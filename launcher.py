"""Standalone Windows controller: single instance, tray, private runtime, health recovery."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Junshi'
DATA.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'engine'))
from securestore import read_json, write_json
INSTANCE = DATA / 'instance.dpapi'
LOG = DATA / 'launcher.log'
K32 = ctypes.WinDLL('kernel32', use_last_error=True)
K32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
K32.CreateMutexW.restype = ctypes.c_void_p
K32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
K32.CreateEventW.restype = ctypes.c_void_p
K32.OpenEventW.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_wchar_p]
K32.OpenEventW.restype = ctypes.c_void_p
K32.SetEvent.argtypes = [ctypes.c_void_p]
K32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
K32.CloseHandle.argtypes = [ctypes.c_void_p]
NAME = hashlib.sha256(str(DATA).lower().encode()).hexdigest()[:20]
STOP_NAME = 'Local\\JunshiStop-' + NAME


def log(message):
    try:
        if LOG.exists() and LOG.stat().st_size > 512000:
            os.replace(LOG, LOG.with_suffix('.previous.log'))
        with LOG.open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(message) + '\n')
    except OSError:
        pass


def api(info, path, post=False):
    request = urllib.request.Request('http://127.0.0.1:' + str(int(info['port'])) + path,
        data=b'{}' if post else None,
        headers={'Authorization':'Bearer ' + info['token'], 'Content-Type':'application/json'})
    # Never use system proxy for local control traffic.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
        return json.load(response)


def open_panel(info):
    url = 'http://127.0.0.1:' + str(int(info['port'])) + '/ui#token=' + info['token']
    edge = next((p for p in [Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe', Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'] if p.is_file()),None)
    try:
        if edge:
            subprocess.Popen([str(edge), '--app='+url, '--window-size=520,820'],creationflags=0x08000000)
        else:
            webbrowser.open(url)
    except OSError:
        webbrowser.open(url)


def notice(text):
    ctypes.windll.user32.MessageBoxW(None,text,'军师',0x40)


def rotate_engine_logs():
    for name in ['.dsh-junshi-engine.log','.dsh-junshi.log']:
        p=DATA/name
        if p.exists() and p.stat().st_size > 1024*1024:
            try: os.replace(p,p.with_suffix('.previous.log'))
            except OSError: pass


def diagnose():
    results={}
    for name in ['numpy','cv2','onnxruntime','rapidocr_onnxruntime','windows_capture','PIL','pystray']:
        try: __import__(name);results[name]='ok'
        except Exception as exc: results[name]=type(exc).__name__
    try:
        write_json(DATA/'diagnostic-check.dpapi',{'test':'ok'})
        results['dpapi']='ok' if read_json(DATA/'diagnostic-check.dpapi') == {'test':'ok'} else 'fail'
        (DATA/'diagnostic-check.dpapi').unlink(missing_ok=True)
    except Exception:results['dpapi']='fail'
    (DATA/'诊断结果.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    notice('诊断完成：'+str(DATA/'诊断结果.json'))
    return 0 if all(v=='ok' for v in results.values()) else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--background',action='store_true')
    parser.add_argument('--stop',action='store_true')
    parser.add_argument('--diagnose',action='store_true')
    args=parser.parse_args()
    if args.diagnose:return diagnose()
    if args.stop:
        event=K32.OpenEventW(2,False,STOP_NAME)
        if event:
            K32.SetEvent(event);K32.CloseHandle(event)
        else:
            try:
                info=read_json(INSTANCE)
                api(info,'/shutdown',post=True)
            except Exception:
                INSTANCE.unlink(missing_ok=True)
                return 0
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if not INSTANCE.exists():return 0
            time.sleep(.2)
        return 1 if INSTANCE.exists() else 0
    mutex=K32.CreateMutexW(None,False,'Local\\JunshiInstance-'+NAME)
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:
        try:
            for _ in range(60):
                try:
                    info=read_json(INSTANCE)
                    if api(info,'/health').get('ok'):
                        if not args.background:open_panel(info)
                        return 0
                except Exception:time.sleep(1)
            if not args.background:notice('军师正在启动或恢复，请稍后双击桌面图标。')
            return 1
        finally:K32.CloseHandle(mutex)
    stop_handle=K32.CreateEventW(None,True,False,STOP_NAME)
    stop=threading.Event();restart=threading.Event();shared={'info':None,'child':None,'icon':None,'paused':True}

    def stop_requested():return stop.is_set() or K32.WaitForSingleObject(stop_handle,0)==0
    def quit_app(icon=None,item=None):stop.set()
    def show(icon=None,item=None):
        if shared['info']:
            threading.Thread(target=open_panel,args=(shared['info'],),daemon=True).start()
    def retry(icon=None,item=None):restart.set()
    def toggle_pause(icon=None,item=None):
        def change():
            try:
                info=shared.get('info')
                if not info:return
                paused=api(info,'/state')['settings']['paused']
                api(info,'/resume' if paused else '/pause',post=True)
                shared['paused']=not paused
                if shared['icon']:shared['icon'].update_menu()
            except Exception:
                if shared['icon']:
                    try:shared['icon'].notify('请先打开军师检查密钥和连接状态。','军师')
                    except Exception:pass
        threading.Thread(target=change,daemon=True).start()

    def supervise():
        failures=[];opened=args.background
        last_panel_port=None
        token=secrets.token_urlsafe(32)
        preferred_port=47830
        try:
            while not stop_requested():
                if len(failures)>=3 and time.monotonic()-failures[-3]<600:
                    log('Recovery paused after three failures; use tray Restart')
                    if shared['icon']:
                        try:shared['icon'].notify('多次启动失败，可右键托盘重启，或查看诊断结果。','军师')
                        except Exception:pass
                    while not stop_requested() and not restart.wait(.5):pass
                    restart.clear();failures=[]
                    if stop_requested():break
                rotate_engine_logs()
                env=os.environ.copy()
                env.update({'DSH_HOME':str(DATA),'DSH_JUNSHI_TOKEN':token,'DSH_JUNSHI_NO_BROWSER':'1','DSH_JUNSHI_PORT':str(preferred_port),'JUNSHI_STANDALONE':'1','PYTHONUTF8':'1'})
                env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
                child=subprocess.Popen([str(ROOT/'runtime/pythonw.exe'),'-X','utf8',str(ROOT/'engine/junshi.py')],cwd=str(ROOT),env=env,creationflags=0x08000000,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                shared['child']=child;info=None
                portfile=DATA/('.dsh-junshi.port.'+''.join(c for c in token if c.isalnum())[:8])
                deadline=time.monotonic()+60
                while child.poll() is None and time.monotonic()<deadline and not stop_requested():
                    try:
                        candidate={'port':int(portfile.read_text().strip()),'token':token,'pid':child.pid}
                        health=api(candidate,'/health')
                        if health.get('ok') and health.get('pid')==child.pid:
                            preferred_port=candidate['port']
                            info=candidate;write_json(INSTANCE,info);shared['info']=info
                            log('Engine ready')
                            if not opened:
                                open_panel(info);opened=True
                            elif last_panel_port is not None and info['port']!=last_panel_port:
                                # 端口漂移（TIME_WAIT 等导致 47830 被占）时重开面板，
                                # 否则旧面板指向死端口，用户只能手动从托盘重开。
                                open_panel(info)
                            last_panel_port=info['port']
                            break
                    except Exception:pass
                    time.sleep(.3)
                misses=0;lastcheck=0
                while info and child.poll() is None and not stop_requested() and not restart.is_set():
                    if time.monotonic()-lastcheck>10:
                        lastcheck=time.monotonic()
                        try:
                            h=api(info,'/health')
                            if not h.get('capture_thread_alive',True) or h.get('heartbeat_age',0)>90:raise RuntimeError('capture unhealthy')
                            paused=h.get('status')=='paused'
                            if paused!=shared['paused']:
                                shared['paused']=paused
                                if shared['icon']:shared['icon'].update_menu()
                            misses=0
                        except Exception:misses+=1
                        if misses>=3:log('Health probe failed three times');break
                    time.sleep(.3)
                if child.poll()==0 and not restart.is_set():
                    stop.set() # Intentional authenticated /shutdown is not a crash.
                if child.poll() is None:
                    try:
                        if info:api(info,'/shutdown',post=True)
                        child.wait(timeout=4)
                    except Exception:
                        child.terminate()
                        try:child.wait(timeout=3)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                shared['info']=None;INSTANCE.unlink(missing_ok=True);portfile.unlink(missing_ok=True)
                if stop_requested():break
                if restart.is_set():restart.clear();failures=[]
                else:failures.append(time.monotonic())
                for _ in range(10):
                    if stop_requested():break
                    time.sleep(.2)
        except Exception as exc:
            import traceback
            log('Controller failed: ' + type(exc).__name__ + ' ' + ' / '.join(traceback.format_exc().splitlines()[-3:])[-400:])
            if not args.background:notice('启动失败，请从开始菜单运行“军师诊断”。')
        finally:
            child=shared.get('child')
            if child and child.poll() is None:
                child.terminate()
            INSTANCE.unlink(missing_ok=True)
            if shared['icon']:shared['icon'].stop()
    try:
        import pystray
        from PIL import Image,ImageDraw
        image=Image.new('RGBA',(64,64),(0,0,0,0));draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((3,3,61,61),radius=16,fill='#22a875')
        draw.rounded_rectangle((14,18,50,44),radius=7,fill='white');draw.polygon([(19,42),(19,51),(30,43)],fill='white')
        icon=pystray.Icon('Junshi',image,'军师 · 微信回复',menu=pystray.Menu(pystray.MenuItem('打开军师',show,default=True),pystray.MenuItem(lambda item:'继续读取' if shared['paused'] else '暂停读取',toggle_pause),pystray.MenuItem('重启服务',retry),pystray.MenuItem('退出军师',quit_app)))
        shared['icon']=icon
        worker=threading.Thread(target=supervise,daemon=True)
        def setup(icon):icon.visible=True;worker.start()
        icon.run(setup=setup);stop.set();worker.join(timeout=10)
    finally:
        K32.CloseHandle(stop_handle);K32.CloseHandle(mutex)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        log('Startup failed: '+type(exc).__name__)
        notice('启动失败，请从开始菜单运行“军师诊断”。')
        sys.exit(1)
