#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import subprocess
import time

# --- CONFIGURAZIONE ---
GITHUB_TOKEN = "***"


# --- FUNZIONI ---
def run_deploy(github_token, module, password):
    cmd = [
        ".venv/bin/ansible-playbook",
        "vulnbox_deploy.yml",
        "-i",
        "vulnbox,",
        "-u",
        "root",
        "--extra-vars",
        f"ansible_user=root ansible_password={password} token={github_token}",
        "--extra-vars",
        "@.env.json",
        "--extra-vars",
        f'{{"modules": ["{module}"]}}',
    ]

    print(f"\n[INFO] Starting deploy for module: {module}\n{'=' * 50}")
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    for line in iter(process.stdout.readline, ""):
        print(f"[{module}] {line.strip()}")

    process.stdout.close()
    returncode = process.wait()

    if returncode == 0:
        print(f"\n[SUCCESS] {module} completed successfully.\n{'=' * 50}")
    else:
        print(f"\n[ERROR] {module} failed with return code {returncode}.\n{'=' * 50}")

    return (module, returncode == 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modules", nargs="+", help="Lista dei moduli da deployare")
    parser.add_argument(
        "--token", default=GITHUB_TOKEN, help="GitHub token for authentication"
    )
    parser.add_argument(
        "--vulnbox-password",
        required=True,
        help="Initial vulnbox root password (before common changes it)",
    )
    args = parser.parse_args()

    selected_modules = args.modules
    github_token = args.token
    initial_password = args.vulnbox_password
    if not selected_modules:
        selected_modules = [
            "common",
            "kickstarterpy",
            "s4dfarm",
            "packmate",
            "threesome",
            "dashboard",
            "wisscon",
        ]

    start_time = time.time()
    kikstarter_flag = False
    deploy_flag = False

    if "common" in selected_modules:
        selected_modules.remove("common")
        # Step 1: deploy common
        print("[STEP 1] Deploying 'common' module...")
        module_common_result = run_deploy(github_token, "common", initial_password)
        if not module_common_result[1]:
            print("[FATAL] 'common' deploy failed. Aborting parallel deploys.")
            return
    if "kickstarterpy" in selected_modules:
        selected_modules.remove("kickstarterpy")
        kikstarter_flag = True

    if "git_deploy" in selected_modules:
        selected_modules.remove("git_deploy")
        deploy_flag = True

    # Step 2: read new root password
    try:
        with open(".env.json") as f:
            data = json.load(f)
        root_password = data["root_password"]
        print(f"\n[INFO] Retrieved updated root password from .env.json.")
    except Exception as e:
        print(f"[ERROR] Failed to read new password: {e}")
        return

    # Step 3: deploy selected modules in parallel
    print("\n[STEP 2] Deploying selected modules in parallel...\n" + "=" * 50)
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(selected_modules)
        ) as executor:
            futures = [
                executor.submit(run_deploy, github_token, mod, root_password)
                for mod in selected_modules
            ]
            for future in concurrent.futures.as_completed(futures):
                module, success = future.result()
                status = "[DONE]" if success else "[FAILED]"
                print(f"[{module}] Deploy result: {status}")
    except Exception as e:
        print(f"[ERROR] An error occurred during parallel deployment: {e}")

    if kikstarter_flag:
        print("[STEP 3] Deploying 'kickstarterpy' module...")
        module_kickstarterpy_result = run_deploy(
            github_token, "kickstarterpy", root_password
        )
        if not module_kickstarterpy_result[1]:
            print("[FATAL] 'kickstarterpy' deploy failed. Aborting parallel deploys.")
            return

    if deploy_flag:
        print("[STEP 4] Deploying 'git_deploy' module...")
        module_git_deploy_result = run_deploy(github_token, "git_deploy", root_password)
        if not module_git_deploy_result[1]:
            print("[FATAL] 'git_deploy' deploy failed. Aborting parallel deploys.")
            return

    # Profiling: tempo totale
    end_time = time.time()
    duration = end_time - start_time
    minutes, seconds = divmod(duration, 60)
    print(f"\n Tempo totale di esecuzione: {int(minutes)} min {seconds:.2f} sec")


if __name__ == "__main__":
    main()
