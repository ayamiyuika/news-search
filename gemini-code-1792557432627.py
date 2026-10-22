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
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "region": "東海",
        "official_domains": ["parque-net.com"],
        "urls": [
            "https://www.parque-net.com/news/",
            "https://www.parque-net.com/",
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
    "企業情報", "サイトマップ", "ニュースリリース", "お知らせ", "新着情報"
}

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


# ==========================================
# 2. 自動エンコーディング解析＆補足情報抽出エンジン
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


def extract_supplementary_info(surrounding_html, title_text, is_pdf=False):
    """タイトルと重複しない補足情報（日時・概要・案内）を抽出"""
    clean = re.sub(r'<script.*?>.*?</script>', ' ', surrounding_html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<style.*?>.*?</style>', ' ', clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = html.unescape(clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    # タイトル部分を除去
    clean = clean.replace(title_text, ' ')
    clean = re.sub(r'(?:令和\s*[0-9０-９元]+年|\d{4}年|\d{1,2}月|\d{1,2}日|[\d\.\/\-\s・\|｜【】\[\]\(\)])+', ' ', clean)
    for g in GENERIC_LINK_TEXTS:
        clean = clean.replace(g, ' ')
    clean = re.sub(r'\s+', ' ', clean).strip()

    # 12文字以上の文を探索
    candidate_sentences = [s.strip() for s in re.split(r'[。！？\n]', clean) if len(s.strip()) >= 12]
    priority_sentences = [s for s in candidate_sentences if re.search(r'(日時|開催|期間|実施|運行|発売|予定|ダイヤ|記念|詳細|対象|開始|運休)', s)]

    if priority_sentences:
        res = "。".join(priority_sentences[:2])
        if not res.endswith("。"):
            res += "。"
        return res[:135] + ("..." if len(res) > 135 else "")
    elif candidate_sentences:
        res = candidate_sentences[0]
        if not res.endswith("。"):
            res += "。"
        return res[:135] + ("..." if len(res) > 135 else "")

    # タイトル重複を避ける実用的な代替案内
    if is_pdf:
        return "公式発表資料（PDF）をご確認ください。実施日程、対象区間・詳細案内が掲載されています。"
    return "公式サイトの発表ページをご確認ください。概要、スケジュール、詳細案内が掲載されています。"


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
                    desc_m = re.search(r"<description>(.*?)</description>", item_xml, flags=re.DOTALL)
                    if
