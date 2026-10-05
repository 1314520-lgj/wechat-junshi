"""Explicit local file import: video frame samples and independent CPU speech decoding."""
import base64,io,json,os,subprocess,sys,tempfile,threading
from pathlib import Path
_lock=threading.Lock()
MAX_BYTES=20*1024*1024

def decode_audio_prefix(executable,path):
    import numpy as np
    output=subprocess.run([executable,'-nostdin','-v','error','-i',str(path),'-t','180','-vn','-ac','1','-ar','16000','-f','f32le','pipe:1'],capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if output.returncode or len(output.stdout)%4 or len(output.stdout)>180*16000*4:
        raise ValueError('语音前180秒解码失败，内容保持未知')
    return np.frombuffer(output.stdout,dtype='<f4')
def visual_sample(message):
    description=message.get('media_description')
    confidence=message.get('vision_confidence')
    reliable=(isinstance(description,str) and bool(description.strip())
              and isinstance(confidence,(int,float)) and not isinstance(confidence,bool)
              and .75<=confidence<=1 and message.get('vision_uncertain') is False
              and message.get('media_understanding_complete') is not False
              and message.get('kind') not in ('audio','video','media_unknown'))
    return {'second':message['sample_second'],'description':description if reliable else None,
            'unverified_description':description if not reliable else None,
            'unknown':not reliable,'crop_id':message.get('media_id'),
            'vision_confidence':confidence,'vision_uncertain':not reliable,
            'scope':'sampled_visible_frame_only'}

def analyze_upload(body,settings,key,progress=None):
    if not _lock.acquire(False):raise ValueError('已有视频或语音正在处理，请等待完成')
    try:
        name=body.get('name','');extension=Path(name).suffix.lower()
        if extension not in ('.mp4','.mov','.mkv','.webm','.wav','.mp3','.m4a','.ogg','.flac','.aac'):raise ValueError('不支持此媒体格式，请先导出常见视频或音频文件')
        encoded=body.get('data','')
        if not isinstance(encoded,str) or len(encoded)>MAX_BYTES*4//3+8:raise ValueError('媒体文件不能超过20MB')
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>MAX_BYTES:raise ValueError('媒体文件不能超过20MB')
        with tempfile.TemporaryDirectory(prefix='junshi-media-') as temporary:
            source=Path(temporary)/('source'+extension);source.write_bytes(raw)
            if progress:progress('speech')
            result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--decode',str(source)],capture_output=True,text=True,encoding='utf-8',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise ValueError('媒体解码或语音模型不可用，请检查文件和本地模型；'+(result.stderr.splitlines() or ['解码进程无错误输出'])[-1][:100])
            decoded=json.loads(result.stdout)
        from media import remember
        from vision import understand
        import numpy as np
        from PIL import Image
        messages=[]
        for item in decoded.pop('frames',[]):
            pixels=np.asarray(Image.open(io.BytesIO(base64.b64decode(item['jpeg']))).convert('RGB'))
            identity=remember(pixels,(0,0,pixels.shape[1],pixels.shape[0]))
            messages.append({'from':'her','text':'','kind':'image','media_id':identity,'sample_second':item['second']})
        import modelrouter
        with modelrouter.session(settings,os.environ.get('DSH_HOME') or os.path.join(os.environ.get('LOCALAPPDATA','.'),'Junshi'),key):
            frames,warnings=understand(messages,settings,key,progress)
        decoded['visual_samples']=[visual_sample(m) for m in frames]
        decoded['warnings']+=warnings;decoded['source']='user_imported_file';decoded['not_a_thumbnail']=True
        decoded['coverage']='视频仅抽样画面；音频最多处理前180秒。抽样之外的画面及未转写语音保持未知。'
        decoded['file_sha256']=__import__('hashlib').sha256(raw).hexdigest();decoded['filename']=Path(name).name
        return decoded
    finally:_lock.release()

def decode_file(path):
    root=Path(__file__).resolve().parent.parent
    sys.path.insert(0,str(root/'media-runtime'))
    import imageio_ffmpeg,re
    from PIL import Image
    executable=imageio_ffmpeg.get_ffmpeg_exe()
    metadata=subprocess.run([executable,'-nostdin','-i',str(path)],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stderr.decode('utf-8','replace')
    match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',metadata)
    duration=sum(float(value)*factor for value,factor in zip(match.groups(),(3600,60,1))) if match else None
    video='Video:' in metadata;audio='Audio:' in metadata
    if not video and not audio:raise ValueError('未能读取有效音视频流，内容保持未知')
    frames=[];warnings=[]
    if video:
        length=min(duration or 30,180)
        for fraction in (.1,.5,.9):
            second=length*fraction
            output=subprocess.run([executable,'-nostdin','-v','error','-ss',str(second),'-i',str(path),'-frames:v','1','-vf','scale=1024:1024:force_original_aspect_ratio=decrease','-f','image2pipe','-vcodec','mjpeg','-'],capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if output.returncode==0 and output.stdout:frames.append({'second':round(second,2),'jpeg':base64.b64encode(output.stdout).decode()})
            else:warnings.append('此抽样画面未能解码，保持未知')
    transcript=[]
    if audio:
        model_dir=root/'models'/'whisper-small'
        if not (model_dir/'model.bin').is_file():warnings.append('本地语音模型尚未安装，语音内容保持未知')
        else:
            import numpy as np
            from faster_whisper import WhisperModel
            samples=decode_audio_prefix(executable,path)
            if len(samples):
                model=WhisperModel(str(model_dir),device='cpu',compute_type='int8',cpu_threads=4)
                segments,info=model.transcribe(samples,beam_size=3,vad_filter=True,condition_on_previous_text=False)
                transcript=[{'start':round(s.start,2),'end':round(s.end,2),'text':s.text,'source':'asr','uncertain':s.avg_logprob < -.8} for s in segments]
                if not transcript:warnings.append('没有识别出可靠语音，保持未知')
    if duration and duration>180:warnings.append('文件超过180秒，未处理部分保持未知')
    return {'duration':duration,'has_video':bool(video),'has_audio':bool(audio),'frames':frames,'transcript':transcript,'warnings':warnings}

if __name__=='__main__' and '--decode' in sys.argv:
    print(json.dumps(decode_file(sys.argv[-1]),ensure_ascii=False))
