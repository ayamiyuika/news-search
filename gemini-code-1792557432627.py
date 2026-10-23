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
import streamlit.components.v1 as components

# 日本標準時（JST）の定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# ページ基本設定
st.set_page_config(
    page_title="全国大手鉄道会社  広報発表・ニュース 概要",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社  広報発表・ニュース 概要")
st.caption("JR・大手私鉄・近鉄グループ各社の公式発表・最新ニュースを一覧表示します。")

# セッションステートの初期化
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()

# ==========================================
# 0. クエリパラメータ（一括選択・解除）の処理
# ==========================================
selected_from_query = []
try:
    if hasattr(st.query_params, "get_all"):
        selected_from_query = st.query_params.get_all("c")
    else:
        val = st.query_params.get("c")
        if isinstance(val, list):
            selected_from_query = val
        elif isinstance(val, str):
            selected_from_query = [val]
except Exception:
    pass

if "submitted" in st.query_params:
    st.session_state.selected_filter_companies = set(selected_from_query)
    st.query_params.clear()
elif "reset" in st.query_params:
    st.session_state.selected_filter_companies.clear()
    st.query_params.clear()

# ==========================================
# 1. 鉄道会社・持株会社・グループ各社のマスタープール
# ==========================================
COMPANY_POOL = {
    # --- JR各社 ---
    "jr-hokkaido": {
        "id": "jr-hokkaido",
        "name": "JR北海道",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道",
    },
    "jr-east": {
        "id": "jr-east",
        "name": "JR東日本",
        "official_domains": ["jreast.co.jp"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/company/",
        ],
        "query": "JR東日本",
    },
    "jr-central": {
        "id": "jr-central",
        "name": "JR東海",
        "official_domains": ["jr-central.co.jp"],
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/news/",
            "https://jr-central.co.jp/",
        ],
        "query": "JR東海 OR 東海旅客鉄道",
    },
    "jr-west": {
        "id": "jr-west",
        "name": "JR西日本",
        "official_domains": ["westjr.co.jp"],
        "urls": [
            "https://www.westjr.co.jp/press/article/",
            "https://www.westjr.co.jp/press/",
        ],
        "query": "JR西日本",
    },
    "jr-shikoku": {
        "id": "jr-shikoku",
        "name": "JR四国",
        "official_domains": ["jr-shikoku.co.jp"],
        "urls": [
            "https://www.jr-shikoku.co.jp/03_news/press/",
            "https://www.jr-shikoku.co.jp/",
        ],
        "query": "JR四国",
    },
    "jr-kyushu": {
        "id": "jr-kyushu",
        "name": "JR九州",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州",
    },
    # --- 私鉄各社 ---
    "tobu": {
        "id": "tobu",
        "name": "東武鉄道",
        "official_domains": ["tobu.co.jp"],
        "urls": ["https://www.tobu.co.jp/newsrelease/"],
        "query": "東武鉄道",
    },
    "seibu": {
        "id": "seibu",
        "name": "西武鉄道（西武HD含む）",
        "official_domains": ["seiburailway.jp", "seibuholdings.co.jp"],
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス",
    },
    "keisei": {
        "id": "keisei",
        "name": "京成電鉄",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/keisei/kouhou/news/index.php",
            "https://www.keisei.co.jp/",
        ],
        "query": "京成電鉄",
    },
    "tokyo-metro": {
        "id": "tokyo-metro",
        "name": "東京メトロ",
        "official_domains": ["tokyometro.jp"],
        "urls": [
            "https://www.tokyometro.jp/news/index.html",
            "https://www.tokyometro.jp/news/rss/news.xml",
            "https://www.tokyometro.jp/",
        ],
        "query": "東京メトロ OR 東京地下鉄",
    },
    "keio": {
        "id": "keio",
        "name": "京王電鉄",
        "official_domains": ["keio.co.jp"],
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
        ],
        "query": "京王電鉄",
    },
    "odakyu": {
        "id": "odakyu",
        "name": "小田急電鉄",
        "official_domains": ["odakyu.jp"],
        "urls": [
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/",
        ],
        "query": "小田急電鉄",
    },
    "tokyu": {
        "id": "tokyu",
        "name": "東急電鉄（東急HD含む）",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
            "https://www.tokyu.co.jp/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    "keikyu": {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/report/",
            "https://www.keikyu.co.jp/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    "sotetsu": {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    "meitetsu": {
        "id": "meitetsu",
        "name": "名古屋鉄道",
        "official_domains": ["meitetsu.co.jp"],
        "urls": [
            "https://www.meitetsu.co.jp/profile/news/",
            "https://www.meitetsu.co.jp/",
        ],
        "query": "名古屋鉄道 OR 名鉄",
    },
    "nankai": {
        "id": "nankai",
        "name": "南海電気鉄道",
        "official_domains": ["nankai.co.jp"],
        "urls": [
            "https://www.nankai.co.jp/news.html",
            "https://www.nankai.co.jp/news/",
            "https://www.nankai.co.jp/",
        ],
        "query": "南海電気鉄道 OR 南海電鉄",
    },
    "keihan": {
        "id": "keihan",
        "name": "京阪電気鉄道（京阪HD含む）",
        "official_domains": ["keihan.co.jp", "keihan-holdings.co.jp"],
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
            "https://www.keihan.co.jp/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
    },
    "osaka-metro": {
        "id": "osaka-metro",
        "name": "大阪メトロ (Osaka Metro)",
        "official_domains": ["osakametro.co.jp"],
        "urls": [
            "https://subway.osakametro.co.jp/news/news_release/",
            "https://subway.osakametro.co.jp/news/",
        ],
        "query": "大阪メトロ OR \"Osaka Metro\"",
    },
    "hanshin": {
        "id": "hanshin",
        "name": "阪神電気鉄道",
        "official_domains": ["hanshin.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hanshin.co.jp/press/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    "hankyu": {
        "id": "hankyu",
        "name": "阪急電鉄",
        "official_domains": ["hankyu.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
    "hankyu-hanshin-hd": {
        "id": "hankyu-hanshin-hd",
        "name": "阪急阪神ホールディングス",
        "official_domains": ["hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu-hanshin.co.jp/release/",
        ],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
    },
    "nishitetsu": {
        "id": "nishitetsu",
        "name": "西日本鉄道",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
    # --- 近鉄グループ（18社：完全指定順） ---
    "kintetsu-ghd": {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD",
    },
    "kintetsu-railway": {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "official_domains": ["kintetsu.co.jp"],
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/all_info/whatsnew.html",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車",
    },
    "kintetsu-fudosan": {
        "id": "kintetsu-fudosan",
        "name": "近鉄不動産",
        "official_domains": ["kintetsu-re.co.jp"],
        "urls": [
            "https://www.kintetsu-re.co.jp/news/",
            "https://www.kintetsu-re.co.jp/corporate/news/",
            "https://www.kintetsu-re.co.jp/corporate/",
        ],
        "query": "近鉄不動産",
    },
    "abeno-art-museum": {
        "id": "abeno-art-museum",
        "name": "あべのハルカス美術館",
        "official_domains": ["aham.jp"],
        "urls": [
            "https://www.aham.jp/news/",
            "https://www.aham.jp/information/",
            "https://www.aham.jp/",
        ],
        "query": "あべのハルカス美術館",
    },
    "kwe": {
        "id": "kwe",
        "name": "近鉄エクスプレス",
        "official_domains": ["kwe.co.jp", "kwe.com"],
        "urls": [
            "https://www.kwe.co.jp/news/",
            "https://www.kwe.co.jp/",
        ],
        "query": "近鉄エクスプレス",
    },
    "kintetsu-dept": {
        "id": "kintetsu-dept",
        "name": "近鉄百貨店",
        "official_domains": ["d-kintetsu.co.jp"],
        "urls": [
            "https://www.d-kintetsu.co.jp/corporate/",
            "https://www.d-kintetsu.co.jp/",
        ],
        "query": "近鉄百貨店",
    },
    "kintetsu-retailing": {
        "id": "kintetsu-retailing",
        "name": "近鉄リテーリング",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/news/",
            "https://knt-rt.co.jp/",
        ],
        "query": "近鉄リテーリング",
    },
    "kinsho-store": {
        "id": "kinsho-store",
        "name": "近商ストア",
        "official_domains": ["kinsho-store.co.jp"],
        "urls": [
            "https://www.kinsho-store.co.jp/html/news.php",
            "https://www.kinsho-store.co.jp/",
        ],
        "query": "近商ストア",
    },
    "miyako-hotels": {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/newsrelease/",
            "https://www.miyakohotels.ne.jp/information/",
            "https://www.miyakohotels.ne.jp/",
        ],
        "query": "近鉄・都ホテルズ OR 都ホテルズ＆リゾーツ OR 都ホテル",
    },
    "knt-ct": {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": "KNT-CTホールディングス OR \"KNT-CT\"",
    },
    "knt": {
        "id": "knt",
        "name": "近畿日本ツーリスト",
        "official_domains": ["knt.co.jp"],
        "urls": [
            "https://corp.knt.co.jp/ja/release/",
            "https://corp.knt.co.jp/",
            "https://www.knt.co.jp/",
        ],
        "query": "近畿日本ツーリスト",
    },
    "club-tourism": {
        "id": "club-tourism",
        "name": "クラブツーリズム",
        "official_domains": ["club-tourism.co.jp", "club-t.com"],
        "urls": [
            "https://www.club-tourism.co.jp/jpn/press/",
            "https://www.club-tourism.co.jp/jpn/",
            "https://www.club-t.com/ct/news/",
        ],
        "query": "クラブツーリズム",
    },
    "kaiyukan": {
        "id": "kaiyukan",
        "name": "海遊館",
        "official_domains": ["kaiyukan.com"],
        "urls": [
            "https://www.kaiyukan.com/topics/",
            "https://www.kaiyukan.com/",
        ],
        "query": "海遊館",
    },
    "shima-spain-village": {
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "official_domains": ["parque-net.com"],
        "urls": [
            "https://www.parque-net.com/press/",
            "https://www.parque-net.com/blog/?cat=7",
        ],
        "query": "志摩スペイン村 OR パルケエスパーニャ",
    },
    "kintetsu-bus": {
        "id": "kintetsu-bus",
        "name": "近鉄バス",
        "official_domains": ["kintetsu-bus.co.jp"],
        "urls": [
            "https://www.kintetsu-bus.co.jp/news/",
            "https://www.kintetsu-bus.co.jp/",
        ],
        "query": "近鉄バス",
    },
    "nara-kotsu": {
        "id": "nara-kotsu",
        "name": "奈良交通",
        "official_domains": ["narakotsu.co.jp"],
        "urls": [
            "https://www.narakotsu.co.jp/news/category/press/",
            "https://www.narakotsu.co.jp/news/",
        ],
        "query": "奈良交通",
    },
    "sanco-hd": {
        "id": "sanco-hd",
        "name": "三交ホールディングス",
        "official_domains": ["holdings.sanco.co.jp"],
        "urls": [
            "https://holdings.sanco.co.jp/news/",
            "https://holdings.sanco.co.jp/",
        ],
        "query": "三交ホールディングス OR 三重交通グループホールディングス",
    },
    "sanco": {
        "id": "sanco",
        "name": "三重交通",
        "official_domains": ["sanco.co.jp"],
        "urls": [
            "https://www.sanco.co.jp/news/",
            "https://www.sanco.co.jp/",
        ],
        "query": "三重交通",
    },
}

JR_ORDER = ["jr-hokkaido", "jr-east", "jr-central", "jr-west", "jr-shikoku", "jr-kyushu"]

PRIVATE_ORDER = [
    "tobu", "seibu", "keisei", "tokyo-metro", "keio", "odakyu",
    "tokyu", "keikyu", "sotetsu", "meitetsu",
    "kintetsu-ghd", "kintetsu-railway",
    "nankai", "keihan", "osaka-metro", "hanshin", "hankyu", "hankyu-hanshin-hd", "nishitetsu"
]

KINTETSU_ORDER = [
    "kintetsu-ghd",
    "kintetsu-railway",
    "kintetsu-fudosan",
    "abeno-art-museum",
    "kwe",
    "kintetsu-dept",
    "kintetsu-retailing",
    "kinsho-store",
    "miyako-hotels",
    "knt-ct",
    "knt",
    "club-tourism",
    "kaiyukan",
    "shima-spain-village",
    "kintetsu-bus",
    "nara-kotsu",
    "sanco-hd",
    "sanco"
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
    "営業時間", "営業カレンダー", "本日のパーク情報", "本日の営業時間",
    "最新のニュース", "最新ニュース", "新着ニュース", "プレスリリース", "新着情報一覧"
}

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


# ==========================================
# 2. 自動エンコーディング解析＆全範囲日付抽出
# ==========================================
def decode_html_bytes(raw_bytes, url=""):
    enc_candidates = []
    if any(d in url for d in ["westjr.co.jp", "kintetsu", "nankai.co.jp", "hanshin.co.jp", "hankyu.co.jp", "keihan.co.jp", "jr-central.co.jp"]):
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


def parse_date_text(raw_text, current_year, prefer_first=False):
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text).translate(zen_to_han)

    # 1. 令和表記
    m_reiwa = list(re.finditer(r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text))
    if m_reiwa:
        match_item = m_reiwa[0] if prefer_first else m_reiwa[-1]
        y_val = 1 if match_item.group(1) == "元" else int(match_item.group(1))
        try:
            return datetime.date(2018 + y_val, int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 2. 平成表記
    m_heisei = list(re.finditer(r"平成\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text))
    if m_heisei:
        match_item = m_heisei[0] if prefer_first else m_heisei[-1]
        y_val = 1 if match_item.group(1) == "元" else int(match_item.group(1))
        try:
            return datetime.date(1988 + y_val, int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 3. 西暦表記
    m_seireki = list(re.finditer(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text))
    if m_seireki:
        match_item = m_seireki[0] if prefer_first else m_seireki[-1]
        try:
            return datetime.date(int(match_item.group(1)), int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 4. 月日のみ
    if re.search(r"(?:19|20)\d{2}", text):
        return None

    m_md = list(re.finditer(r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)", text))
    if m_md:
        match_item = m_md[0] if prefer_first else m_md[-1]
        try:
            return datetime.date(current_year, int(match_item.group(1)), int(match_item.group(2)))
        except ValueError:
            pass

    return None


def clean_leading_date(title):
    if re.match(r"^(?:202\d|令和\s*(?:\d+|元))年度", title):
        return title
    title = re.sub(r"^(?:(?:19|20)\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[:：|｜・\s]*", "", title)
    title = re.sub(r"^(?:(?:19|20)\d{2}年\d{1,2}月\d{1,2}日|令和\s*(?:\d+|元)年\d{1,2}月\d{1,2}日)\s*[:：|｜・\s]+", "", title)
    return title.strip()


def clean_surrounding_html(surrounding):
    first_close = surrounding.find('>')
    first_open = surrounding.find('<')
    if first_close != -1 and (first_open == -1 or first_close < first_open):
        surrounding = surrounding[first_close + 1:]
    
    last_open = surrounding.rfind('<')
    last_close = surrounding.rfind('>')
    if last_open != -1 and (last_close == -1 or last_open > last_close):
        surrounding = surrounding[:last_open]
        
    return surrounding


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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,ja-JP;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": company_info["urls"][0],
        "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
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
                            if any(ng in clean_t for ng in ["営業時間", "営業カレンダー", "最新のニュース"]):
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

                if re.search(r'/(?:20[01]\d|202[0-3])/', full_url):
                    continue

                parsed_u = urllib.parse.urlparse(full_url)
                if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                    continue

                if company_info["id"] == "hanshin" and "hankyu-hanshin.co.jp" in parsed_u.netloc.lower():
                    surrounding_check = clean_html[max(0, m.start() - 200) : min(len(clean_html), m.end() + 200)]
                    if "阪急" in surrounding_check and "阪神" not in surrounding_check:
                        continue

                inside_html = m.group(2)
                start_pos, end_pos = m.start(), m.end()

                before_html = clean_html[max(0, start_pos - 350) : start_pos]
                after_html = clean_html[end_pos : min(len(clean_html), end_pos + 250)]

                found_date = parse_date_text(inside_html, current_year)
                if not found_date:
                    found_date = parse_date_text(before_html, current_year, prefer_first=False)
                if not found_date:
                    found_date = parse_date_text(after_html, current_year, prefer_first=True)

                if not found_date or not (cutoff_date <= found_date <= today):
                    continue

                raw_t = re.sub(r"<[^>]+>", " ", inside_html)
                raw_t = html.unescape(raw_t)
                clean_t = re.sub(r"\s+", " ", raw_t).strip()

                surrounding = clean_html[max(0, start_pos - 350) : min(len(clean_html), end_pos + 250)]
                surrounding = clean_surrounding_html(surrounding)

                if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5 or clean_t == "最新のニュース":
                    h_m = re.findall(r"<h[1-5][^>]*>(.*?)</h[1-5]>", surrounding, flags=re.DOTALL | re.IGNORECASE)
                    if h_m:
                        clean_t = re.sub(r"<[^>]+>", "", h_m[-1]).strip()
                    else:
                        comb = re.sub(r"<[^>]+>", " ", surrounding)
                        comb = html.unescape(comb)
                        lines = [line.strip() for line in comb.split() if len(line.strip()) > 6 and line.strip() not in GENERIC_LINK_TEXTS and line.strip() != "最新のニュース"]
                        if lines:
                            clean_t = lines[0]
                        else:
                            continue

                if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5 or clean_t == "最新のニュース":
                    continue

                if any(bad in clean_t for bad in ['="', "='", "class=", "id=", "style=", "headerMenu", "header", "menu", "<", ">"]):
                    continue

                clean_t = clean_leading_date(clean_t)

                if len(clean_t) < 5 or clean_t in GENERIC_LINK_TEXTS or clean_t == "最新のニュース":
                    continue

                if any(ng in clean_t for ng in ["営業時間", "営業カレンダー", "本日の営業時間"]):
                    continue

                pdf_m = re.search(r'href=["\']([^"\']+\.pdf)["\']', surrounding, re.IGNORECASE)
                detected_pdf = urllib.parse.urljoin(final_base_url, pdf_m.group(1).strip()) if pdf_m else None

                page_url = full_url
                pdf_url = detected_pdf

                if full_url.lower().endswith(".pdf"):
                    pdf_url = full_url
                    page_m = re.search(r'href=["\']([^"\']*(?:page_|article/|detail/)[^"\']*\.html)["\']', surrounding, re.IGNORECASE)
                    if page_m:
                        page_url = urllib.parse.urljoin(final_base_url, page_m.group(1).strip())

                if company_info["id"] == "jr-west" and not pdf_url and page_url.endswith(".html"):
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
                is_pdf = bool(pdf_url or full_url.lower().endswith(".pdf"))

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
                "pdf_url": None,
                "source": source_name,
                "is_pdf": False,
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
# 5. アプリ全体のボタンスタイル定義（濃紺 #1e3a8a 統一）
# ==========================================
st.markdown(
    """
    <style>
    /* アプリ全体の primary ボタン（記事を表示、データ更新、3日間/7日間選択時など）を濃紺に統一 */
    button[kind="primary"],
    button[data-testid="baseButton-primary"],
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #1e3a8a !important;
        border-color: #1e3a8a !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px rgba(30, 58, 138, 0.3) !important;
    }
    button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover,
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #172554 !important;
        border-color: #172554 !important;
        color: #ffffff !important;
    }
    /* secondary ボタン（記事を非表示、未選択時など） */
    button[kind="secondary"],
    button[data-testid="baseButton-secondary"],
    div[data-testid="stButton"] button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #334155 !important;
        border: 1px solid #cbd5e1 !important;
        font-weight: 500 !important;
    }
    button[kind="secondary"]:hover,
    button[data-testid="baseButton-secondary"]:hover,
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background-color: #f8fafc !important;
        color: #1e3a8a !important;
        border-color: #1e3a8a !important;
    }
    /* ラジオボタンなどのアクセントカラーも紺色に統一 */
    input[type="radio"] {
        accent-color: #1e3a8a !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 6. サイドバー操作パネル
# ==========================================
today = datetime.datetime.now(JST).date()

if "date_range" not in st.session_state:
    st.session_state.date_range = (today - datetime.timedelta(days=2), today)
if "selected_period_days" not in st.session_state:
    st.session_state.selected_period_days = 3

with st.sidebar:
    st.header("⚙️ 設定")

    st.write("**1. 対象期間**")

    is_3days = st.session_state.selected_period_days == 3
    type_3 = "primary" if is_3days else "secondary"
    type_7 = "secondary" if is_3days else "primary"

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("📅 3日間", key="btn_period_3", type=type_3, use_container_width=True):
            st.session_state.selected_period_days = 3
            st.session_state.date_range = (today - datetime.timedelta(days=2), today)
            st.rerun()
    with btn_col2:
        if st.button("📅 7日間", key="btn_period_7", type=type_7, use_container_width=True):
            st.session_state.selected_period_days = 7
            st.session_state.date_range = (today - datetime.timedelta(days=6), today)
            st.rerun()

    date_range = st.date_input(
        "対象期間を選択",
        value=st.session_state.date_range,
        max_value=today,
        label_visibility="collapsed",
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
        st.session_state.date_range = (start_date, end_date)
        diff = (end_date - start_date).days + 1
        if diff == 3 and end_date == today:
            st.session_state.selected_period_days = 3
        elif diff == 7 and end_date == today:
            st.session_state.selected_period_days = 7
    else:
        start_date = end_date = date_range[0]

    if st.session_state.hidden_companies:
        if st.button("👁️ すべての会社の記事を再表示", use_container_width=True):
            st.session_state.hidden_companies.clear()
            st.rerun()

    st.markdown("---")
    st.write("**2. 分類**")
    selected_category = st.radio(
        "選択した分類の先頭へスクロールします",
        [
            "すべて",
            "JR",
            "私鉄",
            "近鉄グループ",
        ],
    )

    st.markdown("---")
    st.write("**3. 公式発表・ニュース（一般）**")
    selected_type = st.radio(
        "表示種別",
        ["すべて", "公式発表", "ニュース（一般サイト）"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.write("**4. データ更新**")
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
# 7. データ取得（リアルタイム進行状況目安バー表示）
# ==========================================
unique_company_keys = list(COMPANY_POOL.keys())
total_comps = len(unique_company_keys)
all_cached_data = {}

progress_placeholder = st.empty()

for i, key in enumerate(unique_company_keys):
    comp = COMPANY_POOL[key]
    percent = int(((i + 1) / total_comps) * 100)
    with progress_placeholder.container():
        st.markdown(
            f"""
            <div style="background-color: rgba(30, 58, 138, 0.08); padding: 10px 16px; border-radius: 8px; border: 1px solid rgba(30, 58, 138, 0.3); margin-bottom: 8px;">
                <div style="font-size: 0.95em; font-weight: 700; color: #1e3a8a; margin-bottom: 4px;">
                    🔄 最新データを巡回確認中: {i+1} / {total_comps} 社 ({percent}%)
                </div>
                <div style="font-size: 0.85em; color: #475569;">
                    現在確認中: <b>🏢 {comp['name']}</b>
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

# 表示グループ
jr_list = [COMPANY_POOL[cid] for cid in JR_ORDER]
private_list = [COMPANY_POOL[cid] for cid in PRIVATE_ORDER]
kintetsu_list = [COMPANY_POOL[cid] for cid in KINTETSU_ORDER]

render_groups = [
    ("jr", "JR", jr_list),
    ("private", "私鉄", private_list),
    ("kintetsu", "近鉄グループ", kintetsu_list),
]

target_anchor_map = {
    "すべて": "sec-top",
    "JR": "sec-jr",
    "私鉄": "sec-private",
    "近鉄グループ": "sec-kintetsu",
}
if selected_category in target_anchor_map:
    target_id = target_anchor_map[selected_category]
    components.html(
        f"""
        <script>
        setTimeout(function() {{
            const doc = window.parent.document;
            const el = doc.getElementById('{target_id}');
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
        }}, 150);
        </script>
        """,
        height=0,
        width=0,
    )

# ==========================================
# 8. タイトルのすぐ下：高速複数選択ボタン＆一括確定フォーム
# ==========================================
st.markdown("<div id='sec-top' style='scroll-margin-top: 10px;'></div>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .slim-jump-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 6px;
        margin-bottom: 14px;
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
    /* チェックボックス本体は非表示 */
    .comp-chk {
        display: none !important;
    }
    /* 未選択時の会社ボタン（白地・グレー枠） */
    .comp-label {
        display: inline-block;
        padding: 3px 10px;
        background-color: #ffffff;
        color: #334155;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.28);
        font-size: 0.78em;
        font-weight: 500;
        line-height: 1.5;
        cursor: pointer;
        user-select: none;
        transition: all 0.15s ease;
    }
    .comp-label:hover {
        background-color: #f1f5f9;
        border-color: #1e3a8a;
        color: #1e3a8a;
    }
    /* ★ 選択された会社ボタン（複数選択可能・濃紺 #1e3a8a・白文字） */
    .comp-chk:checked + .comp-label {
        background-color: #1e3a8a !important;
        color: #ffffff !important;
        border-color: #1e3a8a !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px rgba(30, 58, 138, 0.35) !important;
    }
    /* 確定・解除のボタンスタイル */
    .filter-action-bar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 4px;
        margin-bottom: 24px;
    }
    .apply-filter-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 8px 22px;
        background-color: #1e3a8a;
        color: #ffffff !important;
        border: none;
        border-radius: 6px;
        font-size: 0.9em;
        font-weight: 700;
        cursor: pointer;
        box-shadow: 0 2px 4px rgba(30, 58, 138, 0.25);
        transition: all 0.15s ease;
    }
    .apply-filter-btn:hover {
        background-color: #172554;
        box-shadow: 0 4px 6px rgba(30, 58, 138, 0.35);
    }
    .clear-filter-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 7px 18px;
        background-color: #ffffff;
        color: #475569 !important;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        font-size: 0.88em;
        font-weight: 600;
        text-decoration: none !important;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    .clear-filter-btn:hover {
        background-color: #f8fafc;
        color: #1e3a8a !important;
        border-color: #1e3a8a;
    }
    .link-action-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 6px;
        padding: 4px 12px;
        background-color: rgba(30, 58, 138, 0.08);
        color: #1e3a8a !important;
        border: 1px solid rgba(30, 58, 138, 0.35);
        border-radius: 6px;
        font-size: 0.82em;
        font-weight: 600;
        text-decoration: none;
        transition: all 0.15s ease;
    }
    .link-action-btn:hover {
        background-color: #1e3a8a;
        color: #ffffff !important;
        border-color: #1e3a8a;
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
        .filter-action-bar {
            flex-direction: column;
            align-items: stretch;
            gap: 8px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ★ 高速チェックボックス＋ラベル生成（クリック時に即座に青色トグル・リロードなし）
def make_chk_btn_html(comp_list, prefix, selected_set):
    pieces = []
    for c in comp_list:
        cid = c["id"]
        chk_id = f"chk-{prefix}-{cid}"
        checked = "checked" if cid in selected_set else ""
        pieces.append(
            f'<input type="checkbox" name="c" value="{cid}" id="{chk_id}" class="comp-chk" {checked}>'
            f'<label for="{chk_id}" class="comp-label">{c["name"]}</label>'
        )
    return "".join(pieces)

sel_set = st.session_state.selected_filter_companies
has_filter = len(sel_set) > 0

jump_form_html = f"""
<form method="GET" action="" id="company-filter-form">
  <input type="hidden" name="submitted" value="1">
  <div style="margin-top: 10px; margin-bottom: 8px; font-size: 0.9em; font-weight: 600; color: #334155;">
    💡 会社名を押せば、その会社の記事だけを表示することができます。基本は全て表示します。
  </div>
  <div class="slim-jump-container">
    <div class="slim-jump-row">
      <div class="slim-label label-jr">🚆 JR</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(jr_list, 'jr', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-private">🚇 私鉄</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(private_list, 'private', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-kintetsu">🏢 近鉄グループ</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html
