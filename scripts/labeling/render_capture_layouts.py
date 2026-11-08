"""撮影指示の模式図を描く。実写真のGT作成・推論は行わない。"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO/'docs/assets/capture-layouts'


def render():
    specification = json.loads((ASSETS/'layouts.json').read_bytes())
    cards = []
    for layout in specification['layouts']:
        black, white = layout['black'], layout['white']
        sites = [tuple(p) for p in black+white]
        if (len(sites) != len(set(sites)) or any(r not in range(1,20) or c not in range(1,20) for r,c in sites)
                or set(sites) & {(1,1),(1,19),(19,1),(19,19)}):
            raise ValueError('指示図の座標・重複・四隅を確認してください')
        card = Image.new('RGB',(820,900),'#faf9f5')
        draw = ImageDraw.Draw(card)
        title = ImageFont.truetype('meiryo.ttc',27)
        text = ImageFont.truetype('meiryo.ttc',20)
        number = ImageFont.truetype('meiryo.ttc',17)
        role = '開発用' if layout['role']=='development' else '最終確認用・留保'
        draw.text((36,18),f"{layout['code']}  {layout['title']}  [{role}]",fill='#172f31',font=title)
        draw.text((36,62),f'黒 {len(black)} 石 ／ 白 {len(white)} 石　※撮影指示図・GTではありません',fill='#435b60',font=text)
        draw.text((250,94),'奥側（写真の上）　列 →',fill='#435b60',font=text)
        left,top,spacing = 80,174,36
        draw.rectangle((left-20,top-20,left+18*spacing+20,top+18*spacing+20),fill='#dec28a')
        for i in range(19):
            draw.line((left,top+i*spacing,left+18*spacing,top+i*spacing),fill='#65512d',width=1)
            draw.line((left+i*spacing,top,left+i*spacing,top+18*spacing),fill='#65512d',width=1)
            draw.text((left+i*spacing,top-34),str(i+1),fill='#263f43',font=number,anchor='mm')
            draw.text((left-34,top+i*spacing),str(i+1),fill='#263f43',font=number,anchor='mm')
        for r in (4,10,16):
            for c in (4,10,16):
                x,y=left+(c-1)*spacing,top+(r-1)*spacing
                draw.ellipse((x-3,y-3,x+3,y+3),fill='#65512d')
        for color,points in [('black',black),('white',white)]:
            for r,c in points:
                x,y=left+(c-1)*spacing,top+(r-1)*spacing
                draw.ellipse((x-15,y-15,x+15,y+15),fill=color,outline='#252525',width=2)
        draw.text((165,860),'手前・固定カメラ側　／　行は上から1〜19',fill='#263f43',font=text)
        card.save(ASSETS/(layout['code']+'.png'))
        cards.append(card)
    overview = Image.new('RGB',(1640,2700),'#faf9f5')
    for i,card in enumerate(cards):
        overview.paste(card,((i%2)*820,(i//2)*900))
    overview.save(ASSETS/'overview.png')
    print('6配置の指示図を出力しました。写真やGTは変更していません。')


if __name__ == '__main__':
    render()
