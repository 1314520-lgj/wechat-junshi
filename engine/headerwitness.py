"""Read-only selected-sidebar/title agreement. Never authorizes input."""
import unicodedata
import numpy as np
import cv2

def _title(text):
    return unicodedata.normalize('NFC',str(text or '')).strip()

def _rows(rows, crop):
    """OCR output is evidence only after its shape and coordinates are checked."""
    if not isinstance(rows,(list,tuple)):return None
    valid=[]
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=3:return None
        bounds,text,confidence=row
        if not isinstance(text,str):return None
        if not isinstance(confidence,(int,float)) or isinstance(confidence,bool):return None
        if not np.isfinite(confidence) or not 0<=confidence<=1:return None
        try:points=np.asarray(bounds,dtype=float)
        except (ValueError,TypeError,OverflowError):return None
        if points.shape!=(4,2) or not np.isfinite(points).all():return None
        left,right=float(points[:,0].min()),float(points[:,0].max())
        top,bottom=float(points[:,1].min()),float(points[:,1].max())
        if not (0<=left<right<crop.shape[1] and 0<=top<bottom<crop.shape[0]):return None
        if confidence>=.92 and _title(text):valid.append((points,_title(text)))
    return valid

def selected_box(full,pane_x):
    h,w=full.shape[:2]
    # Restrict to the sidebar: outgoing green bubbles are excluded entirely.
    part=full[:,:max(0,int(pane_x)-4)]
    if part.size==0:return None
    r,g,b=part[:,:,0].astype(float),part[:,:,1].astype(float),part[:,:,2].astype(float)
    mask=((g>90)&(g>r*1.5)&(g>b*1.3)).astype(np.uint8)*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=map(int,cv2.boundingRect(contour))
        if not (w*.04<x<pane_x*.5 and bw>pane_x*.4 and 24<bh<h*.15 and y>h*.06):continue
        if not pane_x-32<=x+bw<=pane_x:continue
        if cv2.contourArea(contour)<bw*bh*.90:continue
        boxes.append((x,y,x+bw,y+bh))
    return boxes[0] if len(boxes)==1 else None

def area_from_agreement(full,composer,recognize_details):
    h,w=full.shape[:2];x,y,x1,y1=composer
    selected=selected_box(full,x)
    if selected is None:return None
    sx,sy,sx1,sy1=selected
    # Exclude avatar and preview/time fields; match only the selected name row.
    sidebar=full[sy:sy+int((sy1-sy)*.55),sx+int((sx1-sx)*.25):sx1-int((sx1-sx)*.12)]
    hy=int(h*.025);hend=int(h*.11)
    header=full[hy:hend,x:x+int((x1-x)*.60)]
    try:
        srows=recognize_details(sidebar);hrows=recognize_details(header)
    except Exception:return None
    srows=_rows(srows,sidebar);hrows=_rows(hrows,header)
    # Two readable labels (including duplicates) are ambiguous, not a choice.
    if srows is None or hrows is None or len(srows)!=1:return None
    name=srows[0][1]
    matches=[]
    for points,text in hrows:
        if text!=name:continue
        top,bottom=float(points[:,1].min())+hy,float(points[:,1].max())+hy
        left,right=float(points[:,0].min()),float(points[:,0].max())
        if not (h*.03<=top<bottom<=h*.09 and 4<=bottom-top<=h*.04 and 0<=left<right<header.shape[1]):continue
        matches.append(int(np.ceil(bottom+(bottom-top)*.5)))
    if len(matches)!=1:return None
    top=matches[0]
    if y-top<h*.3:return None
    pixels=full[top:y:8,x:x1:8].reshape(-1,3)
    colors,counts=np.unique(pixels,axis=0,return_counts=True)
    return x,top,x1,y,colors[counts.argmax()],0
