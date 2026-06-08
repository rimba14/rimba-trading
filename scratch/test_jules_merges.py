import subprocess
import logging
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JULES_MERGE_TEST")

def run_cmd(cmd: str) -> str:
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()

def get_remote_branches() -> List[str]:
    stdout = run_cmd("git branch -r")
    branches = []
    for line in stdout.split('\n'):
        branch = line.strip()
        if not branch or '->' in branch or branch == 'origin/main':
            continue
        branches.append(branch)
    return branches

def test_merges():
    branches = get_remote_branches()
    logger.info(f"Found {len(branches)} remote branches.")
    
    successful = 0
    failed = 0
    
    for b in branches:
        # Attempt merge
        logger.info(f"Attempting merge of {b}...")
        res = subprocess.run(f"git merge {b} --no-edit", shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info(f"[SUCCESS] Merged {b}")
            successful += 1
        else:
            logger.warning(f"[CONFLICT] Aborting merge of {b}")
            subprocess.run("git merge --abort", shell=True, capture_output=True)
            failed += 1
            
    logger.info(f"--- MERGE SUMMARY ---")
    logger.info(f"Total Attempted: {len(branches)}")
    logger.info(f"Successfully Merged: {successful}")
    logger.info(f"Conflicts Aborted: {failed}")

if __name__ == "__main__":
    test_merges()
