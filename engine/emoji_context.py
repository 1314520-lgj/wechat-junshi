"""Local symbol names and bounded context hints; names never prove intent.

Unicode/CLDR data license is shipped beside emoji_names.json. WeChat aliases
are explicit text spellings; arbitrary bracketed text is not an emoji.
"""
import json
import re
from pathlib import Path
from functools import lru_cache

_GROUPS={
 'smile':('微笑|Smile','客套、真笑或反话'),
 'joy':('笑哭|破涕为笑|Joy','开心、调侃或苦中作乐'),
 'cover':('捂脸|Facepalm|偷笑|Chuckle','尴尬、自嘲或偷乐'),
 'cry':('大哭|流泪|Sob|Cry','难过、感动或夸张'),
 'thanks':('合十|抱拳|Salute','感谢、请求或致意'),
 'thumb':('强|ThumbsUp','认可、收到或调侃'),
 'heart':('爱心|Heart|拥抱|Hug','亲近、感谢或支持，不证明恋爱关系'),
 'irony':('旺柴|Doge|裂开|Broken|苦涩|翻白眼|白眼','玩笑、自嘲或不满'),
 'other':('呲牙|Grin|调皮|Tongue|害羞|Shy|愉快|Happy|得意|Proud|色|Drool|惊讶|Surprise|委屈|Wronged|可怜|Pity|疑问|Question|疑惑|尴尬|Awkward|汗|Sweat|奋斗|Determined|加油|GoForIt|握手|Handshake|OK|坏笑|Smirk|眨眼|Wink|亲亲|Kiss|再见|Bye|鼓掌|Clap|敬礼|Respect|庆祝|Party|让我看看|LetMeSee|叹气|Sigh|玫瑰|Rose|凋谢|Wilt|嘴唇|Lips|心碎|BrokenHeart|太阳|Sun|月亮|Moon|蛋糕|Cake|礼物|Gift|炸弹|Bomb|骷髅|Skull|便便|Poop|猪头|Pig|咖啡|Coffee|发呆|Daze|睡|Sleep|抓狂|Scream|吐|Puke|嘘|Shhh|衰|鄙视|阴险|左哼哼|右哼哼|打脸|机智|嘿哈|皱眉|悠闲|无语|Emm','含义取决于前文，不固定推断情绪')}
_ALIASES={name.casefold():(name,group) for group,(names,_) in _GROUPS.items() for name in names.split('|')}
_FAMILIES={'🙂':'smile','☺':'smile','😊':'smile','😂':'joy','🤣':'joy','🤭':'cover','🫢':'cover','😢':'cry','😭':'cry','🥹':'cry','🥲':'cry','🙏':'thanks','👍':'thumb','🙃':'irony','🙄':'irony','😅':'cover','😏':'irony'}
_HEARTS='❤💖💕💞💗💓💘💝💜💙💚💛🧡🩷🩵🖤🤍🤎🩶🥰😍😘'
_BRACKET=re.compile(r'\[([^\]\n]{1,24})\]')

@lru_cache(maxsize=1)
def _catalog():
 try:
  names=json.loads(Path(__file__).with_name('emoji_names.json').read_text(encoding='utf-8'))['names']
 except (OSError,ValueError,KeyError):names={}
 trie={}
 for symbol,name in names.items():
  node=trie
  for char in symbol:node=node.setdefault(char,{})
  node['']=name
 return trie

def _matches(text):
 text=str(text or '')[:4000];trie=_catalog();pos=0
 while pos<len(text):
  if text[pos]=='[':
   match=_BRACKET.match(text,pos)
   if match:
    alias=_ALIASES.get(match[1].casefold())
    if alias:
     yield pos,match.end(),match[0],alias[0],alias[1]
     pos=match.end();continue
    # Unknown bracketed data is not silently interpreted via nested Unicode.
    pos=match.end();continue
  node=trie;end=pos;best=None
  while end<len(text) and text[end] in node:
   node=node[text[end]];end+=1
   if '' in node:best=(end,node[''])
  if best:
   end,name=best;symbol=text[pos:end]
   base=re.sub('[\ufe0f\U0001f3fb-\U0001f3ff]','',symbol)
   group=_FAMILIES.get(base,'heart' if base in _HEARTS else 'other')
   yield pos,end,symbol,name,group
   pos=end
  else:pos+=1

def symbols(text,limit=3):
 return [(symbol,name,group) for _,_,symbol,name,group in list(_matches(text))[:limit]]

def emoji_only(text):
 text=str(text or '').strip()
 if not text or len(text)>4000:return False
 end=0;seen=False
 for start,stop,*_ in _matches(text):
  if text[end:start].strip():return False
  end=stop;seen=True
 return seen and not text[end:].strip()

def context_notes(messages):
 hints=[];seen=set();sticker=False
 for m in reversed(list(messages)[-8:]):
  if not isinstance(m,dict) or m.get('from')!='her':continue
  confidence=m.get('vision_confidence',1)
  if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not .75<=confidence<=1:continue
  if m.get('vision_uncertain') or m.get('media_incomplete'):continue
  kind=m.get('kind','text')
  if kind=='sticker':
   sticker=sticker or bool(m.get('media_description'));continue
  if kind not in ('text','emoji','quoted'):continue
  for symbol,name,group in symbols(m.get('text')):
   if symbol in seen:continue
   seen.add(symbol);hints.append(f'{symbol}名称“{name}”；可能用于{_GROUPS[group][1]}')
   if len(hints)>=3:break
  if len(hints)>=3:break
 if not hints and not sticker:return ''
 prefix='表情名称资料不是意图结论；按配字和最近对话区分，优先回应对方表达的事情。'
 if sticker:prefix+='表情包同时看图案、字幕和前文；未知私人梗不猜，字幕不证明本人做过或答应事情。'
 return (prefix+' '.join(hints))[:480]
