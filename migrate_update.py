"""Reversible update migration; preserve keys and disable automatic input."""
from pathlib import Path
import os,json,shutil
home=Path(os.environ['LOCALAPPDATA'])/'Junshi'
path=home/'.dsh-junshi.json'
if path.exists():
    backup=home/'backups/before-1.4.0/.dsh-junshi.json'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(path,backup)
    config=json.loads(path.read_text(encoding='utf-8'))
else:config={};home.mkdir(parents=True,exist_ok=True)
config.update(auto_fill=False,harness_enabled=True)
temp=path.with_suffix('.tmp');temp.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
