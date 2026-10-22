import base64
import datetime
import email.utils
import gzip
import html
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
import streamlit as st

# 日本標準時（JST）の定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# ページ基本設定
st.set_page_config(
    page_title="全国大手鉄道会社  広報発表・ニュース 概要",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社  広報発表・ニュース 概要")
st.caption(
    "JR各社・大手私鉄・地下鉄および近鉄グループ各社の公式ホームページ・最新ニュースを一覧表示します。"
)

# 非表示（折りたたみ）管理用のセッションステート
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()

# ==========================================
# 1. 鉄道会社・持株会社・近鉄グループ各社のマスターデータ
# ==========================================
COMPANIES = [
    # --- JR ---
    {
        "id": "jr-hokkaido",
        "name": "JR北海道",
        "region": "北海道",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    {
        "id": "jr-east",
        "name": "JR東日本",
        "region": "東日本",
        "official_domains": ["jreast.co.jp"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/company/",
        ],
        "query": "JR東日本",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    {
        "id": "jr-central",
        "name": "JR東海",
        "region": "東海",
        "official_domains": ["jr-central.co.jp"],
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/",
        ],
        "query": "JR東海 OR 東海旅客鉄道",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    {
        "id": "jr-west",
        "name": "JR西日本",
        "region": "西日本",
        "official_domains": ["westjr.co.jp"],
        "urls": [
            "https://www.westjr.co.jp/press/article/",
            "https://www.westjr.co.jp/press/",
        ],
        "query": "JR西日本",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    {
        "id": "jr-shikoku",
        "name": "JR四国",
        "region": "四国",
        "official_domains": ["jr-shikoku.co.jp"],
        "urls": [
            "https://www.jr-shikoku.co.jp/03_news/press/",
            "https://www.jr-shikoku.co.jp/",
        ],
        "query": "JR四国",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    {
        "id": "jr-kyushu",
        "name": "JR九州",
        "region": "九州",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州",
        "is_jr": True,
        "is_private": False,
        "is_kintetsu": False,
    },
    # --- 私鉄（近畿日本鉄道を含む） ---
    {
        "id": "tobu",
        "name": "東武鉄道",
        "region": "関東",
        "official_domains": ["tobu.co.jp"],
        "urls": ["https://www.tobu.co.jp/newsrelease/"],
        "query": "東武鉄道",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "seibu",
        "name": "西武鉄道（西武HD含む）",
        "region": "関東",
        "official_domains": ["seiburailway.jp", "seibuholdings.co.jp"],
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "keisei",
        "name": "京成電鉄",
        "region": "関東",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/keisei/kouhou/news/index.php",
            "https://www.keisei.co.jp/",
        ],
        "query": "京成電鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "tokyo-metro",
        "name": "東京メトロ",
        "region": "関東",
        "official_domains": ["tokyometro.jp"],
        "urls": [
            "https://www.tokyometro.jp/news/index.html",
            "https://www.tokyometro.jp/news/rss/news.xml",
        ],
        "query": "東京メトロ OR 東京地下鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "keio",
        "name": "京王電鉄",
        "region": "関東",
        "official_domains": ["keio.co.jp"],
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
        ],
        "query": "京王電鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "odakyu",
        "name": "小田急電鉄",
        "region": "関東",
        "official_domains": ["odakyu.jp"],
        "urls": [
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/",
        ],
        "query": "小田急電鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "tokyu",
        "name": "東急電鉄（東急HD含む）",
        "region": "関東",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "region": "関東",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/",
        ],
        "query": "京浜急行電鉄 OR 京急",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "region": "関東",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "meitetsu",
        "name": "名古屋鉄道",
        "region": "東海",
        "official_domains": ["meitetsu.co.jp"],
        "urls": [
            "https://www.meitetsu.co.jp/profile/news/",
            "https://www.meitetsu.co.jp/",
        ],
        "query": "名古屋鉄道 OR 名鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "region": "関西",
        "official_domains": ["kintetsu.co.jp"],
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": True,
    },
    {
        "id": "nankai",
        "name": "南海電気鉄道",
        "region": "関西",
        "official_domains": ["nankai.co.jp"],
        "urls": [
            "https://www.nankai.co.jp/news.html",
            "https://www.nankai.co.jp/",
        ],
        "query": "南海電気鉄道 OR 南海電鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "keihan",
        "name": "京阪電気鉄道（京阪HD含む）",
        "region": "関西",
        "official_domains": ["keihan.co.jp", "keihan-holdings.co.jp"],
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "osaka-metro",
        "name": "大阪メトロ (Osaka Metro)",
        "region": "関西",
        "official_domains": ["osakametro.co.jp"],
        "urls": [
            "https://subway.osakametro.co.jp/news/news_release/",
            "https://subway.osakametro.co.jp/news/",
        ],
        "query": "大阪メトロ OR \"Osaka Metro\"",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "hanshin",
        "name": "阪神電気鉄道",
        "region": "関西",
        "official_domains": ["hanshin.co.jp"],
        "urls": [
            "https://www.hanshin.co.jp/company/press/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "hankyu",
        "name": "阪急電鉄",
        "region": "関西",
        "official_domains": ["hankyu.co.jp"],
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "hankyu-hanshin-hd",
        "name": "阪急阪神ホールディングス",
        "region": "関西",
        "official_domains": ["hankyu-hanshin.co.jp"],
        "urls": ["https://www.hankyu-hanshin.co.jp/release/"],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    {
        "id": "nishitetsu",
        "name": "西日本鉄道",
        "region": "九州",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
        ],
        "query": "西日本鉄道 OR 西鉄",
        "is_jr": False,
        "is_private": True,
        "is_kintetsu": False,
    },
    # --- 近鉄グループ（ご指定順） ---
    {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "region": "関西",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kintetsu-fudosan",
        "name": "近鉄不動産",
        "region": "関西",
        "official_domains": ["kintetsu-re.co.jp"],
        "urls": [
            "https://www.kintetsu-re.co.jp/news/",
            "https://www.kintetsu-re.co.jp/corporate/news/",
            "https://www.kintetsu-re.co.jp/corporate/",
        ],
        "query": "近鉄不動産",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "abeno-art-museum",
        "name": "あべのハルカス美術館",
        "region": "関西",
        "official_domains": ["aham.jp"],
        "urls": [
            "https://www.aham.jp/news/",
            "https://www.aham.jp/information/",
            "https://www.aham.jp/",
        ],
        "query": "あべのハルカス美術館",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kwe",
        "name": "近鉄エクスプレス",
        "region": "関東・関西",
        "official_domains": ["kwe.co.jp", "kwe.com"],
        "urls": [
            "https://www.kwe.co.jp/news/",
            "https://www.kwe.co.jp/",
        ],
        "query": "近鉄エクスプレス",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kintetsu-dept",
        "name": "近鉄百貨店",
        "region": "関西",
        "official_domains": ["d-kintetsu.co.jp"],
        "urls": [
            "https://www.d-kintetsu.co.jp/corporate/",
            "https://www.d-kintetsu.co.jp/",
        ],
        "query": "近鉄百貨店",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kintetsu-retailing",
        "name": "近鉄リテーリング",
        "region": "関西",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/news/",
            "https://knt-rt.co.jp/",
        ],
        "query": "近鉄リテーリング",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kinsho-store",
        "name": "近商ストア",
        "region": "関西",
        "official_domains": ["kinsho-store.co.jp"],
        "urls": [
            "https://www.kinsho-store.co.jp/html/news.php",
            "https://www.kinsho-store.co.jp/",
        ],
        "query": "近商ストア",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "region": "関西・全国",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/newsrelease/",
            "https://www.miyakohotels.ne.jp/information/",
            "https://www.miyakohotels.ne.jp/",
        ],
        "query": "近鉄・都ホテルズ OR 都ホテルズ＆リゾーツ OR 都ホテル",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "region": "関東・関西",
        "official_domains": ["kntcthd.co.jp", "knt.co.jp", "club-t.com"],
        "urls": [
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": "KNT-CTホールディングス OR 近畿日本ツーリスト OR クラブツーリズム",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kaiyukan",
        "name": "海遊館",
        "region": "関西",
        "official_domains": ["kaiyukan.com"],
        "urls": [
            "https://www.kaiyukan.com/topics/",
            "https://www.kaiyukan.com/",
        ],
        "query": "海遊館",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        # ★ 志摩スペイン村：営業時間リンクの誤認を防ぐためプレスリリース・ブログ広報に限定
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "region": "東海",
        "official_domains": ["parque-net.com"],
        "urls": [
            "https://www.parque-net.com/press/",
            "https://www.parque-net.com/blog/?cat=7",
        ],
        "query": "志摩スペイン村 OR パルケエスパーニャ",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "kintetsu-bus",
        "name": "近鉄バス",
        "region": "関西",
        "official_domains": ["kintetsu-bus.co.jp"],
        "urls": [
            "https://www.kintetsu-bus.co.jp/news/",
            "https://www.kintetsu-bus.co.jp/",
        ],
        "query": "近鉄バス",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "nara-kotsu",
        "name": "奈良交通",
        "region": "関西",
        "official_domains": ["narakotsu.co.jp"],
        "urls": [
            "https://www.narakotsu.co.jp/news/",
            "https://www.narakotsu.co.jp/",
        ],
        "query": "奈良交通",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
    {
        "id": "sanco-hd",
        "name": "三重交通（三交ホールディングス含む）",
        "region": "東海",
        "official_domains": ["holdings.sanco.co.jp", "sanco.co.jp"],
        "urls": [
            "https://holdings.sanco.co.jp/news/",
            "https://www.sanco.co.jp/",
        ],
        "query": "三重交通 OR 三交ホールディングス",
        "is_jr": False,
        "is_private": False,
        "is_kintetsu": True,
    },
]

MEDIA_NAME_MAP = {
    "asahi.com": "朝日新聞デジタル",
    "nikkei.com": "日本経済新聞",
    "yomiuri.co.jp": "読売新聞オンライン",
    "mainichi.jp": "毎日新聞",
    "sankei.com": "産経ニュース",
    "yahoo.co.jp": "Yahoo!ニュース",
    "trafficnews.jp": "乗りものニュース",
    "tetsudo.com": "鉄道コム",
    "railf.jp": "鉄道ファン (railf.jp)",
    "news.mynavi.jp": "マイナビニュース",
    "itmedia.co.jp": "ITmedia",
    "toyokeizai.net": "東洋経済オンライン",
    "diamond.jp": "ダイヤモンド・オンライン",
    "kyodo.co.jp": "共同通信",
    "nordot.app": "ノードット (共同通信系)",
    "jiji.com": "時事通信",
    "nhk.or.jp": "NHK NEWS",
    "kobe-np.co.jp": "神戸新聞NEXT",
    "kyoto-np.co.jp": "京都新聞",
    "chunichi.co.jp": "中日新聞",
    "tokyo-np.co.jp": "東京新聞",
    "hokkaido-np.co.jp": "北海道新聞",
    "nishinippon.co.jp": "西日本新聞",
    "prtimes.jp": "PR TIMES",
    "atpress.ne.jp": "@Press",
    "reuters.com": "ロイター",
    "bloomberg.co.jp": "ブルームバーグ",
    "fnn.jp": "FNNプライムオンライン",
    "tv-asahi.co.jp": "テレ朝news",
    "tbs.co.jp": "TBS NEWS DIG",
    "ntv.co.jp": "日テレNEWS",
}

GENERIC_LINK_TEXTS = {
    "一覧を見る", "ニュース一覧を見る", "お知らせ一覧を見る", "過去の一覧を見る",
    "リリース一覧を見る", "一覧はこちら", "一覧へ", "一覧", "詳しく見る",
    "詳しくはこちら", "詳細を見る", "詳細はこちら", "詳細", "こちら", "もっと見る",
    "記事を読む", "続きを読む", "pdfを見る", "pdfを開く", "pdfダウンロード",
    "pdf", "ダウンロード", "リンク", "次へ", "前へ", "トップへ戻る", "ホーム",
    "企業情報", "サイトマップ", "ニュースリリース", "お知らせ", "新着情報",
    "営業時間", "営業カレンダー", "本日のパーク情報", "本日の営業時間"
}

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


# ==========================================
# 2. 自動エンコーディング解析＆タイトル日付整形
# ==========================================
def decode_html_bytes(raw_bytes, url=""):
    enc_candidates = []
    if "westjr.co.jp" in url:
        enc_candidates.extend(["cp932", "shift_jis"])

    m = re.search(rb'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_\-]+)', raw_bytes[:8192], re.IGNORECASE)
    if not m:
        m = re.search(rb'charset\s*=\s*["\']?\s*([a-zA-Z0-9_\-]+)', raw_bytes[:8192], re.IGNORECASE)
    if m:
        detected = m.group(1).decode("ascii", errors="ignore").lower()
        if detected in ["shift_jis", "sjis", "shift-jis", "x-sjis", "ms932", "windows-31j"]:
            enc_candidates.append("cp932")
        elif detected in ["euc-jp", "euc_jp", "x-euc-jp"]:
            enc_candidates.append("euc_jp")
        elif detected in ["utf-8", "utf8"]:
            enc_candidates.append("utf-8")
        else:
            enc_candidates.append(detected)

    for default_enc in ["utf-8", "cp932", "euc_jp", "shift_jis"]:
        if default_enc not in enc_candidates:
            enc_candidates.append(default_enc)

    best_decoded = None
    for enc in enc_candidates:
        try:
            text = raw_bytes.decode(enc)
            mojibake_count = len(re.findall(r'[縺繧繝譬諷]', text))
            if mojibake_count == 0:
                return text
            if best_decoded is None:
                best_decoded = text
        except (UnicodeDecodeError, LookupError):
            continue

    return best_decoded if best_decoded else raw_bytes.decode("utf-8", errors="replace")


def parse_date_text(raw_text, current_year):
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text).translate(zen_to_han)

    # 令和
    m_reiwa = list(
        re.finditer(
            r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日",
            text,
        )
    )
    if m_reiwa:
        last = m_reiwa[-1]
        y_val = 1 if last.group(1) == "元" else int(last.group(1))
        try:
            return datetime.date(
                2018 + y_val, int(last.group(2)), int(last.group(3))
            )
        except ValueError:
            pass

    # 西暦
    m_seireki = list(
        re.finditer(
            r"(202[0-9])\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?",
            text,
        )
    )
    if m_seireki:
        last = m_seireki[-1]
        try:
            return datetime.date(
                int(last.group(1)), int(last.group(2)), int(last.group(3))
            )
        except ValueError:
            pass

    # 月日のみ
    m_md = list(
        re.finditer(
            r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)",
            text,
        )
    )
    if m_md:
        last = m_md[-1]
        try:
            return datetime.date(
                current_year, int(last.group(1)), int(last.group(2))
            )
        except ValueError:
            pass

    return None


def clean_leading_date(title):
    """
    タイトルの先頭日付のみを安全に除去。
    「2026年度」や「10月18日（日）〇〇開催！」などの重要テキストは絶対に削らない。
    """
    # 「2026年度」や「令和8年度」のように「度」が続くものは絶対に削らない
    if re.match(r"^(?:202\d|令和\s*(?:\d+|元))年度", title):
        return title
    
    # 2026.10.15 / 2026/10/15 / 2026-10-15 のような記号区切りの日付が先頭にある場合
    title = re.sub(r"^(?:202\d[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[:：|｜・\s]*", "", title)
    
    # 2026年10月15日 のような年月日表記で、直後にスペースや区切り記号がある場合のみ
    # （※月日のみで始まるイベント名「10月18日（日）…」は削らない）
    title = re.sub(r"^(?:202\d年\d{1,2}月\d{1,2}日|令和\s*(?:\d+|元)年\d{1,2}月\d{1,2}日)\s*[:：|｜・\s]+", "", title)
    
    return title.strip()


# ==========================================
# 3. スクレイピング（公式・一般ニュース）
# ==========================================
def fetch_official_releases(company_info, max_days_back=21):
    results = []
    seen_urls = set()
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)
    current_year = today.year

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,ja-JP;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    allowed_domains = company_info.get("official_domains", [])

    for url in company_info["urls"]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
                raw_bytes = res.read()
                content_encoding = res.headers.get("Content-Encoding", "").lower()
                final_base_url = res.geturl()

            if content_encoding == "gzip" or raw_bytes[:2] == b"\x1f\x8b":
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    pass
            elif content_encoding == "deflate":
                try:
                    raw_bytes = zlib.decompress(raw_bytes)
                except Exception:
                    pass

            html_text = decode_html_bytes(raw_bytes, url=url)

            # RSSフィード
            if "<rss" in html_text or "<feed" in html_text:
                for item_xml in re.findall(r"<item>(.*?)</item>", html_text, flags=re.DOTALL):
                    t_m = re.search(r"<title>(.*?)</title>", item_xml, flags=re.DOTALL)
                    l_m = re.search(r"<link>(.*?)</link>", item_xml, flags=re.DOTALL)
                    d_m = re.search(r"<(?:pubDate|dc:date)>(.*?)</(?:pubDate|dc:date)>", item_xml, flags=re.DOTALL)
                    if t_m and l_m:
                        t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t_m.group(1)).strip()
                        l = l_m.group(1).strip()
                        d_str = d_m.group(1) if d_m else ""
                        item_date = parse_date_text(d_str, current_year)
                        if item_date and (cutoff_date <= item_date <= today) and l not in seen_urls:
                            clean_t = clean_leading_date(t)
                            if any(ng in clean_t for ng in ["営業時間", "営業カレンダー"]):
                                continue
                            seen_urls.add(l)
                            results.append({
                                "date": item_date,
                                "type": "公式発表",
                                "title": clean_t,
                                "url": l,
                                "pdf_url": l if l.lower().endswith(".pdf") else None,
                                "source": company_info["name"] + " 公式HP",
                                "is_pdf": l.lower().endswith(".pdf"),
                            })
                continue

            # 通常HTML
            clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

            a_matches = list(
                re.finditer(
                    r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                    clean_html,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )

            for m in a_matches:
                raw_href = m.group(1).strip().strip("'\"").replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
                if not raw_href or raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    continue

                full_url = urllib.parse.urljoin(final_base_url, raw_href)
                if full_url in seen_urls:
                    continue

                parsed_u = urllib.parse.urlparse(full_url)
                if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                    continue

                inside_html = m.group(2)
                start_pos, end_pos = m.start(), m.end()
                surrounding = clean_html[
                    max(0, start_pos - 450) : min(len(clean_html), end_pos + 350)
                ]

                found_date = parse_date_text(inside_html, current_year)
                if not found_date:
                    found_date = parse_date_text(surrounding, current_year)

                if not found_date or not (cutoff_date <= found_date <= today):
                    continue

                raw_t = re.sub(r"<[^>]+>", " ", inside_html)
                raw_t = html.unescape(raw_t)
                clean_t = re.sub(r"\s+", " ", raw_t).strip()

                if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5:
                    h_m = re.findall(r"<h[1-5][^>]*>(.*?)</h[1-5]>", surrounding, flags=re.DOTALL | re.IGNORECASE)
                    if h_m:
                        clean_t = re.sub(r"<[^>]+>", "", h_m[-1]).strip()
                    else:
                        comb = re.sub(r"<[^>]+>", " ", surrounding)
                        comb = html.unescape(comb)
                        lines = [line.strip() for line in comb.split() if len(line.strip()) > 6 and line.strip() not in GENERIC_LINK_TEXTS]
                        if lines:
                            clean_t = lines[0]
                        else:
                            continue

                if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5:
                    continue

                # ★ 正しい先頭日付クレンジング（2026年度や西鉄電車まつり等を破壊しない）
                clean_t = clean_leading_date(clean_t)

                if len(clean_t) < 5 or clean_t in GENERIC_LINK_TEXTS:
                    continue

                # 志摩スペイン村等の営業時間リンクを除外
                if any(ng in clean_t for ng in ["営業時間", "営業カレンダー", "本日の営業時間"]):
                    continue

                pdf_m = re.search(r'href=["\']([^"\']+\.pdf)["\']', surrounding, re.IGNORECASE)
                detected_pdf = urllib.parse.urljoin(final_base_url, pdf_m.group(1).strip()) if pdf_m else None

                page_url = full_url
                pdf_url = detected_pdf

                if full_url.lower().endswith(".pdf"):
                    pdf_url = full_url
                    page_m = re.search(r'href=["\']([^"\']*(?:page_|article/)[^"\']*\.html)["\']', surrounding, re.IGNORECASE)
                    if page_m:
                        page_url = urllib.parse.urljoin(final_base_url, page_m.group(1).strip())

                if company_info["name"] == "JR西日本" and not pdf_url and page_url.endswith(".html"):
                    try:
                        sub_req = urllib.request.Request(page_url, headers=headers)
                        with urllib.request.urlopen(sub_req, context=ctx, timeout=3) as sub_res:
                            sub_b = sub_res.read()
                            sub_h = decode_html_bytes(sub_b, url=page_url)
                            inner_pdf_m = re.search(r'href=["\']([^"\']+\.pdf)["\']', sub_h, re.IGNORECASE)
                            if inner_pdf_m:
                                pdf_url = urllib.parse.urljoin(page_url, inner_pdf_m.group(1).strip())
                    except Exception:
                        pass

                seen_urls.add(full_url)
                is_pdf = bool(pdf_url or full_url.lower().endswith(".pdf") or "pdf" in surrounding.lower())

                results.append({
                    "date": found_date,
                    "type": "公式発表",
                    "title": clean_t[:130],
                    "url": page_url,
                    "pdf_url": pdf_url,
                    "source": company_info["name"] + " 公式HP",
                    "is_pdf": is_pdf,
                })
        except Exception:
            pass

    return results


def fetch_general_news(query, max_days_back=21):
    results = []
    encoded_q = urllib.parse.quote(query)
    rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
            xml_data = res.read()
            if xml_data[:2] == b"\x1f\x8b":
                xml_data = gzip.decompress(xml_data)

        root = ET.fromstring(xml_data)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            desc_el = item.find("description")

            if title_el is None or link_el is None:
                continue

            raw_title = title_el.text or ""
            link = (link_el.text or "").strip()
            pubdate_str = pubdate_el.text if pubdate_el is not None else ""
            desc = desc_el.text or ""

            if not link or "news.google.com" in link:
                continue

            if "bing.com" in link:
                u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', link)
                if u_match:
                    try:
                        b64_str = u_match.group(1)
                        b64_str += '=' * (-len(b64_str) % 4)
                        decoded_bytes = base64.urlsafe_b64decode(b64_str)
                        real_url = decoded_bytes.decode('utf-8', errors='ignore')
                        if real_url.startswith("http"):
                            link = real_url
                    except Exception:
                        pass

            item_date = None
            if pubdate_str:
                try:
                    dt = email.utils.parsedate_to_datetime(pubdate_str)
                    jst = dt.astimezone(JST)
                    item_date = jst.date()
                except Exception:
                    pass

            if not item_date or not (cutoff_date <= item_date <= today):
                continue

            clean_title = raw_title.strip()
            clean_desc = re.sub(r"<[^>]+>", " ", desc)
            clean_desc = html.unescape(clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            summary = clean_desc if len(clean_desc) > 10 else clean_title

            if summary == clean_title or len(summary) < 15:
                summary = "報道機関のニュース掲載ページをご確認ください。記事の全文および関連情報が掲載されています。"

            source_name = ""
            for child in item:
                tag_name = child.tag.split("}")[-1].lower()
                if "source" in tag_name:
                    txt = (child.text or "").strip()
                    if txt and txt.lower() not in ["bing", "bing.com"]:
                        source_name = txt
                        break

            if not source_name or source_name.lower() in ["bing", "bing.com"]:
                if " - " in clean_title:
                    parts = clean_title.rsplit(" - ", 1)
                    cand = parts[1].strip()
                    clean_title = parts[0].strip()
                    if cand and cand.lower() not in ["bing", "bing.com"]:
                        source_name = cand

            parsed_url = urllib.parse.urlparse(link)
            domain = parsed_url.netloc.lower().replace("www.", "")

            for domain_key, media_label in MEDIA_NAME_MAP.items():
                if domain_key in domain:
                    source_name = media_label
                    break

            if not source_name or source_name.lower() in ["bing", "bing.com"]:
                source_name = domain if "bing" not in domain else "ニュース報道"

            results.append({
                "date": item_date,
                "type": "ニュース（一般サイト）",
                "title": clean_title,
                "summary": summary[:140] + ("..." if len(summary) > 140 else ""),
                "url": link,
                "pdf_url": link if link.lower().endswith(".pdf") else None,
                "source": source_name,
                "is_pdf": link.lower().endswith(".pdf"),
            })
    except Exception:
        pass

    return results


# ==========================================
# 4. 社別データキャッシュエンジン（1時間保持）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_company_data(company_dict, max_days_back=21):
    official = fetch_official_releases(company_dict, max_days_back=max_days_back)
    general = []
    if "query" in company_dict:
        general = fetch_general_news(company_dict["query"], max_days_back=max_days_back)

    combined = list(official)
    seen_urls = {item["url"] for item in official}
    for g in general:
        if g["url"] not in seen_urls:
            seen_urls.add(g["url"])
            combined.append(g)

    return combined


# ==========================================
# 5. サイドバー操作パネル
# ==========================================
today = datetime.datetime.now(JST).date()
default_start = today - datetime.timedelta(days=7)

with st.sidebar:
    st.header("⚙️ 表示・絞り込み設定")

    st.write("**1. 表示形式**")
    
    st.caption("▼ 対象期間")
    date_range = st.date_input(
        "開始日と終了日を選択",
        value=(default_start, today),
        max_value=today,
        label_visibility="collapsed",
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range[0]

    st.caption("▼ 表示内容")
    display_mode = st.radio(
        "表示内容を選択",
        ["見出し＋概要", "見出しのみ"],
        label_visibility="collapsed",
    )

    if st.session_state.hidden_companies:
        if st.button("👁️ すべての会社の記事を再表示", use_container_width=True):
            st.session_state.hidden_companies.clear()
            st.rerun()

    st.markdown("---")
    st.write("**2. 会社・種別の絞り込み**")

    selected_category = st.radio(
        "会社分類",
        [
            "すべて",
            "JR",
            "私鉄",
            "近鉄グループ",
        ],
    )

    selected_type = st.radio(
        "発表・記事の種別",
        ["すべて", "公式発表", "ニュース（一般サイト）"],
    )

    search_keyword = st.text_input("キーワード検索", "")

    st.markdown("---")
    st.write("**3. データ更新制御**")
    st.caption("※サーバー負荷軽減のため、取得結果は1時間キャッシュ（自動記憶）されます。")
    if st.button("🔄 キャッシュを破棄して最新取得", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_fetch_time = datetime.datetime.now(JST)
        st.rerun()

    st.markdown("---")
    st.caption(
        "**【免責事項】**\n"
        "本サイトは公開情報を自動収集・整理して表示する個人開発ツールです。各鉄道会社および関連企業とは一切関係ありません。情報の完全性・正確性を保証するものではありません。"
    )

# ==========================================
# 6. データ取得（リアルタイム進行状況目安バー表示）
# ==========================================
total_comps = len(COMPANIES)
all_cached_data = {}

progress_placeholder = st.empty()

for i, comp in enumerate(COMPANIES):
    percent = int(((i + 1) / total_comps) * 100)
    with progress_placeholder.container():
        st.markdown(
            f"""
            <div style="background-color: rgba(2, 132, 199, 0.08); padding: 10px 16px; border-radius: 8px; border: 1px solid rgba(2, 132, 199, 0.3); margin-bottom: 8px;">
                <div style="font-size: 0.95em; font-weight: 700; color: #0284c7; margin-bottom: 4px;">
                    🔄 最新データを巡回確認中: {i+1} / {total_comps} 社 ({percent}%)
                </div>
                <div style="font-size: 0.85em; color: #475569;">
                    現在確認中: <b>🏢 {comp['name']}</b> （{comp['region']}）
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress((i + 1) / total_comps)

    items = get_single_company_data(comp, max_days_back=21)
    all_cached_data[comp["name"]] = items

progress_placeholder.empty()

if "last_fetch_time" not in st.session_state:
    st.session_state.last_fetch_time = datetime.datetime.now(JST)

st.caption(f"🕒 最終巡回時刻: {st.session_state.last_fetch_time.strftime('%Y-%m-%d %H:%M:%S')} (日本時間) （1時間ごとに自動再巡回）")

# 表示対象の会社リストの決定
if selected_category == "JR":
    render_groups = [("JR", [c for c in COMPANIES if c["is_jr"]])]
elif selected_category == "私鉄":
    render_groups = [("私鉄", [c for c in COMPANIES if c["is_private"]])]
elif selected_category == "近鉄グループ":
    render_groups = [("近鉄グループ", [c for c in COMPANIES if c["is_kintetsu"]])]
else:
    render_groups = [
        ("JR", [c for c in COMPANIES if c["is_jr"]]),
        ("私鉄", [c for c in COMPANIES if c["is_private"]]),
        ("近鉄グループ", [c for c in COMPANIES if c["is_kintetsu"] and not c["is_private"]]),
    ]

# ==========================================
# 7. タイトルのすぐ下：見出し文字を大きくしたクイックジャンプ
# ==========================================
st.markdown(
    """
    <style>
    .slim-jump-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 8px;
        margin-bottom: 24px;
        padding: 12px 16px;
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 8px;
    }
    .slim-jump-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 2px 0;
    }
    .slim-label {
        flex-shrink: 0;
        width: 140px;
        font-weight: 800;
        font-size: 1.15em;
        line-height: 1.3;
    }
    .label-jr { color: #0284c7; }
    .label-private { color: #10b981; }
    .label-kintetsu { color: #f59e0b; }
    .slim-btn-wrapper {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        flex-grow: 1;
    }
    .slim-btn {
        display: inline-block;
        padding: 3px 10px;
        background-color: var(--secondary-background-color, #ffffff);
        color: var(--text-color, #1f2937);
        text-decoration: none;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.25);
        font-size: 0.78em;
        font-weight: 500;
        line-height: 1.5;
        transition: all 0.15s ease;
    }
    .slim-btn:hover {
        background-color: #0284c7;
        color: #ffffff !important;
        border-color: #0284c7;
        text-decoration: none;
    }
    .link-action-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 6px;
        padding: 4px 12px;
        background-color: rgba(2, 132, 199, 0.08);
        color: #0284c7 !important;
        border: 1px solid rgba(2, 132, 199, 0.35);
        border-radius: 6px;
        font-size: 0.82em;
        font-weight: 600;
        text-decoration: none;
        transition: all 0.15s ease;
    }
    .link-action-btn:hover {
        background-color: #0284c7;
        color: #ffffff !important;
        border-color: #0284c7;
        text-decoration: none;
    }
    @media (max-width: 768px) {
        .slim-jump-row {
            flex-direction: column;
            align-items: flex-start;
            gap: 4px;
        }
        .slim-label {
            width: auto;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

jr_buttons = [c for c in COMPANIES if c["is_jr"]] if selected_category in ["すべて", "JR"] else []
private_buttons = [c for c in COMPANIES if c["is_private"]] if selected_category in ["すべて", "私鉄"] else []
kintetsu_buttons = [c for c in COMPANIES if c["is_kintetsu"]] if selected_category in ["すべて", "近鉄グループ"] else []

def make_slim_btn_html(comp_list):
    if not comp_list:
        return "<span style='font-size:0.75em; color:gray;'>（選択対象外）</span>"
    return "".join([f"<a href='#{c['id']}' class='slim-btn'>{c['name']}</a>" for c in comp_list])

jump_html = f"""
<div class="slim-jump-container">
  <div class="slim-jump-row">
    <div class="slim-label label-jr">🚆 JR</div>
    <div class="slim-btn-wrapper">
      {make_slim_btn_html(jr_buttons)}
    </div>
  </div>
  <div class="slim-jump-row">
    <div class="slim-label label-private">🚇 私鉄</div>
    <div class="slim-btn-wrapper">
      {make_slim_btn_html(private_buttons)}
    </div>
  </div>
  <div class="slim-jump-row">
    <div class="slim-label label-kintetsu">🏢 近鉄グループ</div>
    <div class="slim-btn-wrapper">
      {make_slim_btn_html(kintetsu_buttons)}
    </div>
  </div>
</div>
"""

st.markdown(jump_html, unsafe_allow_html=True)

# ==========================================
# 8. 結果の描画（公式発表はタイトルのみ・主な内容は削除）
# ==========================================
for group_title, comp_list in render_groups:
    st.write("<br>", unsafe_allow_html=True)
    st.markdown(f"## 【 {group_title} 】")
    st.divider()

    for comp in comp_list:
        raw_items = all_cached_data.get(comp["name"], [])

        period_items = [
            item for item in raw_items
            if start_date <= item["date"] <= end_date
        ]

        if search_keyword:
            kw = search_keyword.lower()
            period_items = [
                item
                for item in period_items
                if kw in item["title"].lower()
                or kw in item.get("summary", "").lower()
                or kw in comp["name"].lower()
            ]

        official_items = [i for i in period_items if i["type"] == "公式発表"]
        general_items = [i for i in period_items if i["type"] == "ニュース（一般サイト）"]

        official_items.sort(key=lambda x: x["date"], reverse=True)
        general_items.sort(key=lambda x: x["date"], reverse=True)

        if selected_type == "公式発表":
            display_items = official_items
        elif selected_type == "ニュース（一般サイト）":
            display_items = general_items
        else:
            display_items = official_items + general_items

        main_url = comp["urls"][0]
        is_hidden = comp["id"] in st.session_state.hidden_companies

        h_col1, h_col2 = st.columns([5, 1.3])
        with h_col1:
            st.markdown(
                f"""
                <div id='{comp['id']}' style='margin-top: 18px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 3px solid #0284c7; display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px;'>
                    <span style='font-size: 1.85em; font-weight: 800; color: #1e293b; line-height: 1.2;'>🏢 {comp['name']}</span>
                    <span style='font-size: 1.05em; color: gray; font-weight: 500;'>（{comp['region']}）</span>
                    <a href='{main_url}' target='_blank' rel='noopener noreferrer' style='font-size: 0.9em; font-weight: 600; color: #0284c7; text-decoration: none;'>[公式HP ↗]</a>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col2:
            st.write("<div style='margin-top: 22px;'></div>", unsafe_allow_html=True)
            btn_label = "記事を表示" if is_hidden else "記事を非表示"
            btn_type = "primary" if is_hidden else "secondary"
            if st.button(btn_label, key=f"btn_toggle_{comp['id']}", type=btn_type, use_container_width=True):
                if is_hidden:
                    st.session_state.hidden_companies.remove(comp["id"])
                else:
                    st.session_state.hidden_companies.add(comp["id"])
                st.rerun()

        if is_hidden:
            st.write("")
            continue

        if not display_items:
            type_label = f"（{selected_type}）" if selected_type != "すべて" else ""
            st.info(f"📅 指定期間・条件内の発表{type_label}は **なし** です。")
            st.write("")
        else:
            for item in display_items:
                is_official = item["type"] == "公式発表"

                if is_official:
                    type_badge = (
                        "<div style='display:inline-block; padding:3px 10px; background-color:#1e3a8a; "
                        "color:#ffffff; font-size:0.8em; font-weight:700; border-radius:5px; margin-bottom:4px; "
                        "box-shadow: 0 1px 2px rgba(0,0,0,0.15); letter-spacing:0.04em;'>📢 公式発表</div>"
                    )
                else:
                    type_badge = (
                        "<div style='display:inline-block; padding:3px 9px; background-color:#f1f5f9; "
                        "color:#475569; font-size:0.78em; font-weight:600; border-radius:5px; "
                        "border:1px solid #cbd5e1; margin-bottom:4px;'>📰 ニュース（一般）</div>"
                    )

                if comp["name"] == "JR西日本":
                    title_link = item["url"]
                    action_link = item.get("pdf_url") or item["url"]
                    action_caption = "掲載資料（PDF）を開く ↗"
                    file_badge = "🟥 **[PDF資料]**"
                else:
                    title_link = item["url"]
                    action_link = item.get("pdf_url") or item["url"]
                    action_caption = "掲載資料（PDF）を開く ↗" if item["is_pdf"] else "掲載ページを開く ↗"
                    file_badge = "🟥 **[PDF資料]**" if item["is_pdf"] else "🌐 **[Web発表]**"

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge, unsafe_allow_html=True)
                        st.markdown(file_badge)
                        st.caption(f"情報元: {item['source']}")
                    with col_right:
                        # タイトルリンク
                        st.markdown(
                            f"##### <a href='{title_link}' target='_blank' rel='noopener noreferrer'>{item['title']}</a>",
                            unsafe_allow_html=True,
                        )

                        # ★公式発表はタイトルのみ（主な内容欄は削除）
                        # 一般ニュースのみ、「見出し＋概要」選択時にサマリーを表示
                        if not is_official and display_mode == "見出し＋概要" and item.get("summary"):
                            st.write(f"**主な内容:** {item['summary']}")

                        # 掲載ボタン
                        st.markdown(
                            f"<a href='{action_link}' target='_blank' rel='noopener noreferrer' class='link-action-btn'>🔗 {action_caption}</a>",
                            unsafe_allow_html=True,
                        )
            st.write("")

# フッター免責事項
st.write("---")
st.caption(
    "© 鉄道広報・ニュース概要 | 本アプリは各社公式ホームページおよび報道ニュースを巡回・整理して提供しています。リンク先コンテンツの著作権は各社に帰属します。"
)
