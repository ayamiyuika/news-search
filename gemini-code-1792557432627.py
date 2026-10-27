import base64
import datetime
import email.utils
import gzip
import html
import http.cookiejar
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
    page_title="全国大手鉄道会社 公式発表・ニュース 概要",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 公式発表・ニュース 概要")
st.caption("JR・大手私鉄・近鉄グループ各社の公式発表・最新ニュースを一覧表示します。")

# ==========================================
# 0. メディア優先度＆ナビゲーション除外ブラックリスト
# ==========================================
MEDIA_PRIORITY = {
    "NHK NEWS": 100,
    "日本経済新聞": 95,
    "読売新聞オンライン": 90,
    "朝日新聞デジタル": 90,
    "共同通信": 85,
    "毎日新聞": 85,
    "産経ニュース": 85,
    "時事通信": 80,
    "Yahoo!ニュース": 75,
    "乗りものニュース": 72,
    "鉄道コム": 70,
    "鉄道ファン (railf.jp)": 70,
    "マイナビニュース": 65,
    "東洋経済オンライン": 65,
    "ITmedia": 60,
    "ダイヤモンド・オンライン": 60,
    "FNNプライムオンライン": 55,
    "テレ朝news": 55,
    "TBS NEWS DIG": 55,
    "日テレNEWS": 55,
    "神戸新聞NEXT": 50,
    "京都新聞": 50,
    "中日新聞": 50,
    "東京新聞": 50,
    "北海道新聞": 50,
    "西日本新聞": 50,
}

# ナビゲーション固定メニューの誤取得を徹底的に防ぐ除外リスト
NAV_EXCLUDE_WORDS = {
    "キャラクター", "インスタ映え", "アトラクション", "関連事業", "採用情報", "リンク集",
    "会社概要", "経営理念", "企業情報", "サイトマップ", "プライバシーポリシー", "アクセス",
    "お問い合わせ", "よくあるご質問", "電子公告", "運賃", "時刻表", "路線図", "サービス",
    "ハーベス", "kinsho", "店舗情報", "チラシ情報", "もっと見る", "もっと、", "一覧",
    "ホーム", "top", "トップ", "企業・ir情報", "企業サイト", "安全報告書", "役員一覧",
    "組織図", "沿革", "次へ", "前へ", "« 前ページへ", "前ページへ »", "次ページへ", "«", "»"
}

# セッションステートの初期化
today = datetime.datetime.now(JST).date()

if "show_official" not in st.session_state:
    st.session_state.show_official = True     # デフォルト：公式発表ON（青色）
if "show_news" not in st.session_state:
    st.session_state.show_news = False        # デフォルト：ニュースOFF（灰色）
if "period_days" not in st.session_state:
    st.session_state.period_days = 3          # デフォルト：3日間
if "custom_date_range" not in st.session_state:
    st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()
if "diag_logs" not in st.session_state:
    st.session_state.diag_logs = {}

# ==========================================
# 1. 会社マスタープール（東京メトロ・大阪メトロ完全削除、海遊館なし）
# ==========================================
COMPANY_POOL = {
    # --- JR各社 ---
    "jr-hokkaido": {
        "id": "jr-hokkaido",
        "name": "JR北海道",
        "top_url": "https://www.jrhokkaido.co.jp/",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道 OR 北海道旅客鉄道",
    },
    # ★ JR東日本（公式直結 ＋ 公式site検索救済の二重系）
    "jr-east": {
        "id": "jr-east",
        "name": "JR東日本",
        "is_jr_east": True,
        "top_url": "https://www.jreast.co.jp/",
        "official_domains": ["jreast.co.jp"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/rss/press.xml",
            "https://www.jreast.co.jp/",
        ],
        "query": "JR東日本 OR 東日本旅客鉄道",
    },
    "jr-central": {
        "id": "jr-central",
        "name": "JR東海",
        "top_url": "https://jr-central.co.jp/",
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
        "top_url": "https://www.westjr.co.jp/",
        "official_domains": ["westjr.co.jp"],
        "urls": [
            "https://www.westjr.co.jp/press/article/",
            "https://www.westjr.co.jp/press/",
            "https://www.westjr.co.jp/",
        ],
        "query": "JR西日本 OR 西日本旅客鉄道",
    },
    "jr-shikoku": {
        "id": "jr-shikoku",
        "name": "JR四国",
        "top_url": "https://www.jr-shikoku.co.jp/",
        "official_domains": ["jr-shikoku.co.jp"],
        "urls": [
            "https://www.jr-shikoku.co.jp/03_news/press/",
            "https://www.jr-shikoku.co.jp/",
        ],
        "query": "JR四国 OR 四国旅客鉄道",
    },
    "jr-kyushu": {
        "id": "jr-kyushu",
        "name": "JR九州",
        "top_url": "https://www.jrkyushu.co.jp/",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/news/",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州 OR 九州旅客鉄道",
    },
    # --- 私鉄各社（東京メトロ・大阪メトロ完全削除） ---
    "tobu": {
        "id": "tobu",
        "name": "東武鉄道",
        "top_url": "https://www.tobu.co.jp/",
        "official_domains": ["tobu.co.jp"],
        "urls": [
            "https://www.tobu.co.jp/newsrelease/",
            "https://www.tobu.co.jp/",
        ],
        "query": "東武鉄道",
    },
    "seibu": {
        "id": "seibu",
        "name": "西武鉄道（西武HD含む）",
        "top_url": "https://www.seiburailway.jp/",
        "official_domains": ["seiburailway.jp", "seibuholdings.co.jp"],
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
            "https://www.seiburailway.jp/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス",
    },
    "keisei": {
        "id": "keisei",
        "name": "京成電鉄",
        "top_url": "https://www.keisei.co.jp/",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/",
            "https://www.keisei.co.jp/news/",
        ],
        "query": "京成電鉄",
    },
    "keio": {
        "id": "keio",
        "name": "京王電鉄",
        "top_url": "https://www.keio.co.jp/",
        "official_domains": ["keio.co.jp"],
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
            "https://www.keio.co.jp/",
        ],
        "query": "京王電鉄",
    },
    "odakyu": {
        "id": "odakyu",
        "name": "小田急電鉄",
        "top_url": "https://www.odakyu.jp/",
        "official_domains": ["odakyu.jp"],
        "urls": [
            "https://www.odakyu.jp/",
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/news/",
        ],
        "query": "小田急電鉄",
    },
    # ★ 東急電鉄
    "tokyu": {
        "id": "tokyu",
        "name": "東急電鉄（東急HD含む）",
        "top_url": "https://www.tokyu.co.jp/",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    "keikyu": {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "top_url": "https://www.keikyu.co.jp/",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/",
            "https://www.keikyu.co.jp/report/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    # ★ 相模鉄道（トップページのプレスリリースタブを最優先）
    "sotetsu": {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "top_url": "https://www.sotetsu.co.jp/",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/",
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    "meitetsu": {
        "id": "meitetsu",
        "name": "名古屋鉄道",
        "top_url": "https://www.meitetsu.co.jp/",
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
        "top_url": "https://www.nankai.co.jp/",
        "official_domains": ["nankai.co.jp"],
        "urls": [
            "https://www.nankai.co.jp/news.html",
            "https://www.nankai.co.jp/company/news/",
            "https://www.nankai.co.jp/news/",
            "https://www.nankai.co.jp/",
        ],
        "query": "南海電気鉄道 OR 南海電鉄",
    },
    "keihan": {
        "id": "keihan",
        "name": "京阪電気鉄道（京阪HD含む）",
        "top_url": "https://www.keihan.co.jp/",
        "official_domains": ["keihan.co.jp", "keihan-holdings.co.jp"],
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
            "https://www.keihan.co.jp/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
    },
    "hanshin": {
        "id": "hanshin",
        "name": "阪神電気鉄道",
        "top_url": "https://www.hanshin.co.jp/",
        "official_domains": ["hanshin.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hanshin.co.jp/press/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    # ★ 阪急電鉄
    "hankyu": {
        "id": "hankyu",
        "name": "阪急電鉄",
        "top_url": "https://www.hankyu.co.jp/",
        "official_domains": ["hankyu.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu.co.jp/company/news/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
    # ★ 阪急阪神HD
    "hankyu-hanshin-hd": {
        "id": "hankyu-hanshin-hd",
        "name": "阪急阪神ホールディングス",
        "top_url": "https://www.hankyu-hanshin.co.jp/",
        "official_domains": ["hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu-hanshin.co.jp/",
        ],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
    },
    "nishitetsu": {
        "id": "nishitetsu",
        "name": "西日本鉄道",
        "top_url": "https://www.nishitetsu.co.jp/",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
            "https://www.nishitetsu.co.jp/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
    # --- 近鉄グループ（17社・海遊館なし） ---
    # ★ 近鉄GHD
    "kintetsu-ghd": {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "top_url": "https://www.kintetsu-g-hd.co.jp/",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD OR 近鉄グループ",
    },
    # ★ 近畿日本鉄道
    "kintetsu-railway": {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "top_url": "https://www.kintetsu.co.jp/",
        "official_domains": ["kintetsu.co.jp"],
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/all_info/whatsnew.html",
            "https://www.kintetsu.co.jp/all_news/",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車 OR 近鉄特急",
    },
    "kintetsu-fudosan": {
        "id": "kintetsu-fudosan",
        "name": "近鉄不動産",
        "top_url": "https://www.kintetsu-re.co.jp/",
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
        "top_url": "https://www.aham.jp/",
        "official_domains": ["aham.jp"],
        "urls": [
            "https://www.aham.jp/news/",
            "https://www.aham.jp/information/",
            "https://www.aham.jp/",
        ],
        "query": '"あべのハルカス美術館"',
    },
    "kwe": {
        "id": "kwe",
        "name": "近鉄エクスプレス",
        "top_url": "https://www.kwe.co.jp/",
        "official_domains": ["kwe.co.jp", "kwe.com"],
        "urls": [
            "https://www.kwe.co.jp/news/",
            "https://www.kwe.co.jp/",
        ],
        "query": '"近鉄エクスプレス"',
    },
    # ★ 近鉄百貨店
    "kintetsu-dept": {
        "id": "kintetsu-dept",
        "name": "近鉄百貨店",
        "top_url": "https://www.d-kintetsu.co.jp/",
        "official_domains": ["d-kintetsu.co.jp"],
        "urls": [
            "https://www.d-kintetsu.co.jp/",
            "https://www.d-kintetsu.co.jp/corporate/ir/whatsnew.html",
            "https://www.d-kintetsu.co.jp/corporate/",
        ],
        "query": '"近鉄百貨店"',
    },
    "kintetsu-retailing": {
        "id": "kintetsu-retailing",
        "name": "近鉄リテーリング",
        "top_url": "https://knt-rt.co.jp/",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/",
            "https://knt-rt.co.jp/news/",
        ],
        "query": '"近鉄リテーリング"',
    },
    # ★ 近商ストア
    "kinsho-store": {
        "id": "kinsho-store",
        "name": "近商ストア",
        "top_url": "https://www.kinshostore.co.jp/",
        "official_domains": ["kinsho-store.co.jp", "kinshostore.co.jp"],
        "urls": [
            "https://www.kinshostore.co.jp/html/news.php",
            "https://www.kinsho-store.co.jp/html/news.php",
            "https://www.kinshostore.co.jp/",
        ],
        "query": '"近商ストア"',
    },
    # ★ 近鉄・都ホテルズ
    "miyako-hotels": {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "top_url": "https://www.miyakohotels.ne.jp/",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/",
            "https://www.miyakohotels.ne.jp/newsrelease/",
        ],
        "query": '"近鉄・都ホテルズ" OR "都ホテルズ＆リゾーツ" OR "都ホテル"',
    },
    # ★ KNT-CTホールディングス
    "knt-ct": {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "top_url": "https://www.kntcthd.co.jp/",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
            "https://www.kntcthd.co.jp/release/",
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": '"KNT-CTホールディングス" OR "KNT-CT"',
    },
    "knt": {
        "id": "knt",
        "name": "近畿日本ツーリスト",
        "top_url": "https://corp.knt.co.jp/",
        "official_domains": ["knt.co.jp"],
        "urls": [
            "https://corp.knt.co.jp/ja/release/",
            "https://corp.knt.co.jp/",
            "https://www.knt.co.jp/",
        ],
        "query": '"近畿日本ツーリスト"',
    },
    "club-tourism": {
        "id": "club-tourism",
        "name": "クラブツーリズム",
        "top_url": "https://www.club-tourism.co.jp/",
        "official_domains": ["club-tourism.co.jp", "club-t.com"],
        "urls": [
            "https://www.club-tourism.co.jp/jpn/press/",
            "https://www.club-tourism.co.jp/jpn/",
            "https://www.club-t.com/ct/news/",
        ],
        "query": '"クラブツーリズム"',
    },
    "shima-spain-village": {
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "top_url": "https://parque-net.com/",
        "official_domains": ["parque-net.com"],
        "urls": [
            "https://www.parque-net.com/press/",
            "https://www.parque-net.com/blog/?cat=7",
        ],
        "query": '"志摩スペイン村" OR "パルケエスパーニャ"',
    },
    "kintetsu-bus": {
        "id": "kintetsu-bus",
        "name": "近鉄バス",
        "top_url": "https://www.kintetsu-bus.co.jp/",
        "official_domains": ["kintetsu-bus.co.jp"],
        "urls": [
            "https://www.kintetsu-bus.co.jp/news/",
            "https://www.kintetsu-bus.co.jp/",
        ],
        "query": '"近鉄バス"',
    },
    "nara-kotsu": {
        "id": "nara-kotsu",
        "name": "奈良交通",
        "top_url": "https://www.narakotsu.co.jp/",
        "official_domains": ["narakotsu.co.jp"],
        "urls": [
            "https://www.narakotsu.co.jp/news/category/press/",
            "https://www.narakotsu.co.jp/news/",
        ],
        "query": '"奈良交通"',
    },
    # ★ 三交ホールディングス
    "sanco-hd": {
        "id": "sanco-hd",
        "name": "三交ホールディングス",
        "top_url": "https://holdings.sanco.co.jp/",
        "official_domains": ["holdings.sanco.co.jp", "sanco.co.jp"],
        "urls": [
            "https://holdings.sanco.co.jp/news/",
            "https://holdings.sanco.co.jp/",
            "https://www.sanco.co.jp/allnews/",
        ],
        "query": '"三交ホールディングス" OR "三重交通グループホールディングス"',
    },
    # ★ 三重交通
    "sanco": {
        "id": "sanco",
        "name": "三重交通",
        "top_url": "https://www.sanco.co.jp/",
        "official_domains": ["sanco.co.jp"],
        "urls": [
            "https://www.sanco.co.jp/allnews/",
            "https://www.sanco.co.jp/other/newsrelease/",
            "https://www.sanco.co.jp/",
        ],
        "query": '"三重交通"',
    },
}

JR_ORDER = ["jr-hokkaido", "jr-east", "jr-central", "jr-west", "jr-shikoku", "jr-kyushu"]

# 東京メトロ・大阪メトロを完全削除した私鉄順序
PRIVATE_ORDER = [
    "tobu", "seibu", "keisei", "keio", "odakyu",
    "tokyu", "keikyu", "sotetsu", "meitetsu",
    "kintetsu-ghd", "kintetsu-railway",
    "nankai", "keihan", "hanshin", "hankyu", "hankyu-hanshin-hd", "nishitetsu"
]

# 近鉄グループ17社（海遊館なし）
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
    "reuters.com": "ロイター",
    "bloomberg.co.jp": "ブルームバーグ",
    "fnn.jp": "FNNプライムオンライン",
    "tv-asahi.co.jp": "テレ朝news",
    "tbs.co.jp": "TBS NEWS DIG",
    "ntv.co.jp": "日テレNEWS",
}

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


# ==========================================
# 2. 自動エンコーディング解析＆日付抽出ユーティリティ
# ==========================================
def decode_html_bytes(raw_bytes, url=""):
    enc_candidates = []
    if any(d in url for d in ["westjr.co.jp", "kintetsu", "nankai.co.jp", "hanshin.co.jp", "hankyu.co.jp", "keihan.co.jp", "jr-central.co.jp", "knt-rt.co.jp", "kinsho", "sanco"]):
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
    if not raw_text:
        return None

    # datetime属性の検出
    attr_match = re.search(r'(?:datetime|data-date)=["\']((?:19|20)\d{2}[-/\.][0-9]{1,2}[-/\.][0-9]{1,2})', raw_text, re.IGNORECASE)
    if attr_match:
        try:
            parts = [int(p) for p in re.split(r'[-/\.]', attr_match.group(1))]
            return datetime.date(parts[0], parts[1], parts[2])
        except Exception:
            pass

    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = text.translate(zen_to_han)

    # 1. 令和表記
    m_reiwa = re.search(r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text)
    if m_reiwa:
        y_val = 1 if m_reiwa.group(1) == "元" else int(m_reiwa.group(1))
        try:
            return datetime.date(2018 + y_val, int(m_reiwa.group(2)), int(m_reiwa.group(3)))
        except ValueError:
            pass

    # 2. 西暦表記（2026/10/22, 2026.10.22, 2026-10-22, 2026年10月22日）
    m_seireki = re.search(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text)
    if m_seireki:
        try:
            return datetime.date(int(m_seireki.group(1)), int(m_seireki.group(2)), int(m_seireki.group(3)))
        except ValueError:
            pass

    # 3. 月日のみ表記
    if not re.search(r"(?:19|20)\d{2}", text):
        m_md = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)", text)
        if m_md:
            try:
                return datetime.date(current_year, int(m_md.group(1)), int(m_md.group(2)))
            except ValueError:
                pass

    return None


def clean_extracted_title(raw_title, company_info):
    # まずHTMLタグを完全に除去
    t = re.sub(r"<[^>]*>", " ", raw_title)
    t = html.unescape(t)

    # 先頭の日付表記を除去
    t = re.sub(r"^(?:(?:19|20)\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[:：|｜・\s]*", "", t)
    t = re.sub(r"^(?:(?:19|20)\d{2}年\d{1,2}月\d{1,2}日|令和\s*(?:\d+|元)年\d{1,2}月\d{1,2}日)\s*[:：|｜・\s]+", "", t)

    # 定型会社名や接頭辞の除去
    t = re.sub(r"^(?:東急電鉄|京急電鉄|近畿日本鉄道|プレスリリース|ニュースリリース|お知らせ|PRESS\s*RELEASE|NEWS|重要|電鉄|グループ)\s*", "", t.strip(), flags=re.IGNORECASE)

    # 近商ストア専用クレンジング（属性残骸・サービス名除去）
    if company_info["id"] == "kinsho-store":
        t = re.sub(r'(?:NEW|新着|お知らせ|重要|\.pdf|\.PDF)+', '', t).strip()
        t = re.sub(r'^[【\[（\(].*?[】\]）\)]', '', t).strip()
        t = re.sub(r'^[a-zA-Z0-9_\-]+["\']?>', '', t).strip()

    # 三交ホールディングス・三重交通
    if company_info["id"] in ["sanco-hd", "sanco"]:
        t = re.sub(r'(?:グループニュース|IRニュース|お知らせ|ニュースリリース)+', '', t).strip()
        t = re.sub(r'#448073;padding:[^;]*;', '', t).strip()

    if company_info["id"] == "nara-kotsu":
        t = re.sub(r'^(?:総合路線バス|路線バス|臨時バス|高速バス|貸切バス|観光バス)+', '', t).strip()

    t = re.sub(r"\s+", " ", t).strip()

    # ★ ナビゲーション固定語句・短文単語の完全除外
    t_lower = t.lower()
    if t_lower in NAV_EXCLUDE_WORDS or any(w == t for w in NAV_EXCLUDE_WORDS):
        return ""
    if len(t) < 8:  # 8文字未満の短い単語リンクは公式発表の見出しではないため排除
        return ""

    return t


def clean_news_summary(summary, title, company_name):
    clean = re.sub(r"<[^>]+>", " ", summary)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    noise_terms = [
        "招待券", "プレゼント", "懸賞", "合唱団", "定期演奏会",
        "【新機能】", "writevideo", "プレスリリース *",
        "tel：", "年中無休", "お問合せ 一般のお客様", "お問い合わせ先", "チケット"
    ]
    if any(ng in clean.lower() for ng in noise_terms):
        return f"{company_name}に関する最新の報道・ニュースです。詳細は掲載ページをご確認ください。"

    clean = re.sub(r'[\d\s\.\»\«\>]+最新のニュース.*', '', clean)
    clean = clean.strip()

    if len(clean) < 15 or clean == title:
        return f"{company_name}に関する最新の報道・ニュースです。詳細は掲載ページをご確認ください。"

    return clean[:140] + ("..." if len(clean) > 140 else "")


# ==========================================
# 3. HTTP通信ユーティリティ（最新WAF完全回避セッション）
# ==========================================
@st.cache_resource
def get_advanced_http_opener():
    cookie_jar = http.cookiejar.CookieJar()
    ctx = ssl._create_unverified_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=ctx)
    )
    return opener

def fetch_url_html(url, referer, headers, ctx):
    try:
        opener = get_advanced_http_opener()
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if referer:
            h["Referer"] = referer
        else:
            p = urllib.parse.urlparse(url)
            h["Referer"] = f"{p.scheme}://{p.netloc}/"

        req = urllib.request.Request(url, headers=h)
        with opener.open(req, timeout=9) as res:
            raw_bytes = res.read()
            content_encoding = res.headers.get("Content-Encoding", "").lower()
            final_url = res.geturl()

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

        html_text = decode_html_bytes(raw_bytes, url=final_url)
        return html_text, final_url, "OK"
    except urllib.error.HTTPError as he:
        return "", url, f"HTTP {he.code}"
    except Exception as e:
        return "", url, str(e)


# ==========================================
# 4. 厳格ペアリング公式発表抽出エンジン（行・カード完結型）
# ==========================================
def parse_official_releases_strict(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = company_info.get("official_domains", [])
    cid = company_info["id"]
    is_jr_east = company_info.get("is_jr_east", False)

    # 1. RSS/Atom フィード（最優先解析）
    if "<rss" in html_text or "<feed" in html_text or "<rdf:RDF" in html_text:
        for item_xml in re.findall(r"<(?:item|entry)>(.*?)</(?:item|entry)>", html_text, flags=re.DOTALL):
            t_m = re.search(r"<title>(.*?)</title>", item_xml, flags=re.DOTALL)
            l_m = re.search(r"<link(?:>|\s+[^>]*?href=[\"']([^\"']+)[\"'])", item_xml, flags=re.DOTALL)
            d_m = re.search(r"<(?:pubDate|dc:date|updated)>(.*?)</(?:pubDate|dc:date|updated)>", item_xml, flags=re.DOTALL)
            if t_m and l_m:
                t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t_m.group(1)).strip()
                l = l_m.group(1).strip() if l_m.group(1) else re.search(r"<link>(.*?)</link>", item_xml, flags=re.DOTALL).group(1).strip()
                l = urllib.parse.urljoin(base_url, l)
                d_str = d_m.group(1) if d_m else ""
                item_date = parse_date_text(d_str, current_year)
                if item_date and (cutoff_date <= item_date <= today) and l not in seen_urls:
                    clean_t = clean_extracted_title(t, company_info)
                    if clean_t:
                        seen_urls.add(l)
                        results.append({
                            "date": item_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if l.lower().split('?')[0].endswith(".pdf") else None,
                            "source": company_info["name"] + " 公式HP",
                            "is_pdf": l.lower().split('?')[0].endswith(".pdf"),
                        })
        if results:
            return results

    # 2. スクリプト・スタイルの事前クレンジング
    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<svg.*?>.*?</svg>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # ★ パターン1: 構造ブロック単位（行 <tr>、定義リスト <dl>/<dt>/<dd>、リスト <li>、カード <article>）の解析
    # ナビゲーションメニューを拾わないよう、要素単位で日付とリンクが共存しているものを優先
    block_patterns = [
        r'(<tr[^>]*>.*?</tr>)',
        r'(<li[^>]*>.*?</li>)',
        r'(<article[^>]*>.*?</article>)',
        r'(<div[^>]*class=["\'][^"\']*(?:news|topics|release|press|item)[^"\']*["\'][^>]*>.*?</div>)',
    ]

    for b_pat in block_patterns:
        for block in re.findall(b_pat, clean_html, flags=re.DOTALL | re.IGNORECASE):
            d_val = parse_date_text(block, current_year)
            if not d_val or not (cutoff_date <= d_val <= today):
                continue

            for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE):
                href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
                if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    continue

                full_url = urllib.parse.urljoin(base_url, href)
                if full_url in seen_urls:
                    continue

                if not is_jr_east:
                    parsed_u = urllib.parse.urlparse(full_url)
                    if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                        continue

                clean_t = clean_extracted_title(a_m.group(2), company_info)
                if not clean_t:
                    # ブロック全体のテキストから探す
                    clean_block_txt = re.sub(r"<[^>]+>", " ", block)
                    clean_t = clean_extracted_title(clean_block_txt, company_info)

                if not clean_t:
                    continue

                seen_urls.add(full_url)
                is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
                results.append({
                    "date": d_val,
                    "type": "公式発表",
                    "title": clean_t[:130],
                    "url": full_url,
                    "pdf_url": full_url if is_pdf else None,
                    "source": company_info["name"] + " 公式発表",
                    "is_pdf": is_pdf,
                })

    # ★ パターン2: 近鉄各社などの <dt>日付</dt><dd>リンク</dd> 定義リスト直結構造
    dt_dd_pattern = r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>'
    for m in re.finditer(dt_dd_pattern, clean_html, flags=re.DOTALL | re.IGNORECASE):
        dt_txt = m.group(1)
        dd_txt = m.group(2)
        d_val = parse_date_text(dt_txt, current_year)
        if not d_val or not (cutoff_date <= d_val <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', dd_txt, flags=re.DOTALL | re.IGNORECASE):
            href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            clean_t = clean_extracted_title(a_m.group(2), company_info)
            if not clean_t:
                continue

            seen_urls.add(full_url)
            is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
            results.append({
                "date": d_val,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    # ★ パターン3: カード型リンク内包日付（東急、京急等）
    p_inside = r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>'
    for m in re.finditer(p_inside, clean_html, re.IGNORECASE):
        href = m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        body = m.group(2)
        d_val = parse_date_text(body, current_year)
        if not d_val or not (cutoff_date <= d_val <= today):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        if not is_jr_east:
            parsed_u = urllib.parse.urlparse(full_url)
            if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                continue

        clean_t = clean_extracted_title(body, company_info)
        if not clean_t:
            continue

        seen_urls.add(full_url)
        is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
        results.append({
            "date": d_val,
            "type": "公式発表",
            "title": clean_t[:130],
            "url": full_url,
            "pdf_url": full_url if is_pdf else None,
            "source": company_info["name"] + " 公式発表",
            "is_pdf": is_pdf,
        })

    return results


# ==========================================
# 5. 公式発表 取得ディスパッチャー（JR東日本完全救済ルート搭載）
# ==========================================
def fetch_official_releases(company_info, max_days_back=21):
    results = []
    seen_urls = set()
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)
    current_year = today.year
    cid = company_info["id"]

    ctx = ssl._create_unverified_context()
    log_entry = {
        "tried_urls": [],
        "success_count": 0,
        "status": "INIT"
    }

    # 1. 登録URLの直接巡回
    has_403 = False
    for url in company_info["urls"]:
        html_text, final_url, status = fetch_url_html(url, company_info.get("top_url", url), {}, ctx)
        log_entry["tried_urls"].append(f"{url} -> [{status}]")
        if "403" in status:
            has_403 = True

        if html_text:
            items = parse_official_releases_strict(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)
            if results:
                break

    # 2. トップページの再探索（未取得時）
    if not results and company_info.get("top_url") and not has_403:
        top_html, final_top_url, status = fetch_url_html(company_info["top_url"], "", {}, ctx)
        log_entry["tried_urls"].append(f"TOP: {company_info['top_url']} -> [{status}]")
        if top_html:
            items = parse_official_releases_strict(top_html, final_top_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)

    # 3. ★ JR東日本公式発表 救済エンジン（WAF 403遮断・社内制限を完全突破）
    if cid == "jr-east" and (not results or has_403):
        rescue_q = "site:jreast.co.jp/press"
        encoded_q = urllib.parse.quote(rescue_q)
        rescue_rss = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"
        try:
            req = urllib.request.Request(rescue_rss, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, context=ctx, timeout=6) as r_res:
                x_data = r_res.read()
                if x_data[:2] == b"\x1f\x8b":
                    x_data = gzip.decompress(x_data)
                root = ET.fromstring(x_data)
                for item in root.findall(".//item"):
                    t_el = item.find("title")
                    l_el = item.find("link")
                    d_el = item.find("pubDate")
                    if t_el is None or l_el is None:
                        continue
                    l = (l_el.text or "").strip()
                    if "bing.com" in l:
                        u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', l)
                        if u_match:
                            try:
                                b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) % 4)
                                l = base64.urlsafe_b64decode(b64_str).decode('utf-8', errors='ignore')
                            except Exception:
                                pass

                    if "jreast.co.jp" not in l or l in seen_urls:
                        continue

                    i_date = None
                    if d_el is not None and d_el.text:
                        try:
                            dt = email.utils.parsedate_to_datetime(d_el.text).astimezone(JST)
                            i_date = dt.date()
                        except Exception:
                            pass

                    if i_date and (cutoff_date <= i_date <= today):
                        clean_t = clean_extracted_title(t_el.text or "", company_info)
                        if not clean_t:
                            continue
                        seen_urls.add(l)
                        is_pdf = l.lower().split('?')[0].endswith(".pdf")
                        results.append({
                            "date": i_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if is_pdf else None,
                            "source": "JR東日本 公式発表",
                            "is_pdf": is_pdf,
                        })
            log_entry["tried_urls"].append(f"JR-East Official Rescue Route: {len(results)}件救済取得")
        except Exception as e:
            log_entry["tried_urls"].append(f"JR-East Rescue Error: {e}")

    log_entry["success_count"] = len(results)
    log_entry["status"] = "SUCCESS" if results else "ZERO"
    st.session_state.diag_logs[company_info["name"]] = log_entry

    return results


# ==========================================
# 6. 一般ニュース取得エンジン（完全復元版）
# ==========================================
def fetch_general_news(query, company_dict, max_days_back=21):
    raw_results = []
    company_name = company_dict["name"]
    encoded_q = urllib.parse.quote(query)
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"

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
            desc = desc_el.text if desc_el is not None else ""

            if not link or "news.google.com" in link:
                continue

            if "bing.com" in link:
                u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', link)
                if u_match:
                    try:
                        b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) % 4)
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

            combined_text = (clean_title + " " + clean_desc).lower()

            noise_keywords = [
                "招待券", "プレゼント", "懸賞", "合唱団", "定期演奏会",
                "警察weekly", "県警weekly", "現行犯逮捕", "酒酔い運転", "ひき逃げ",
                "安全運転管理者", "死亡事故", "容疑で逮捕", "書類送検"
            ]
            if any(ng in combined_text for ng in noise_keywords):
                continue

            # 各社の通称・別名判定（近鉄、阪急などの取りこぼしを完全解消）
            strict_companies = ["奈良交通", "近鉄バス", "三重交通", "志摩スペイン村", "あべのハルカス美術館"]
            if company_name in strict_companies:
                if company_name not in clean_title:
                    continue
            else:
                clean_comp = company_name.replace("（", "").replace("）", "")
                comp_keywords = [clean_comp]
                if "・" in clean_comp:
                    comp_keywords.extend(clean_comp.split("・"))
                if "近鉄" in clean_comp:
                    comp_keywords.extend(["近鉄", "近畿日本鉄道"])
                if "阪急" in clean_comp:
                    comp_keywords.extend(["阪急", "阪急電車"])
                if not any(kw.lower() in combined_text for kw in comp_keywords):
                    continue

            summary = clean_news_summary(clean_desc, clean_title, company_name)

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

            priority = MEDIA_PRIORITY.get(source_name, 10)

            raw_results.append({
                "date": item_date,
                "type": "ニュース（一般サイト）",
                "title": clean_title,
                "summary": summary,
                "url": link,
                "pdf_url": None,
                "source": source_name,
                "is_pdf": False,
                "priority": priority,
            })
    except Exception:
        pass

    # 同一見出し重複排除（メジャー媒体優先）
    deduped_dict = {}
    for item in raw_results:
        norm_key = re.sub(r'[\s\u3000・―\-―：:【】「」『』\(\)]+', '', item['title']).lower()
        if norm_key in deduped_dict:
            if item["priority"] > deduped_dict[norm_key]["priority"]:
                deduped_dict[norm_key] = item
        else:
            deduped_dict[norm_key] = item

    return list(deduped_dict.values())


# ==========================================
# 7. 社別キャッシュエンジン
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_company_data(company_dict, max_days_back=21, cache_version="v2026_strict_block_and_nav_filter_v16"):
    official = fetch_official_releases(company_dict, max_days_back=max_days_back)
    general = []
    if "query" in company_dict:
        general = fetch_general_news(company_dict["query"], company_dict, max_days_back=max_days_back)

    combined = list(official)
    seen_urls = {item["url"] for item in official}
    for g in general:
        if g["url"] not in seen_urls:
            seen_urls.add(g["url"])
            combined.append(g)

    return combined


# ==========================================
# 8. アプリ全体のボタンスタイル定義（濃紺 #1e3a8a 統一）
# ==========================================
st.markdown(
    """
    <style>
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
    button[kind="secondary"],
    button[data-testid="baseButton-secondary"],
    div[data-testid="stButton"] button[kind="secondary"],
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background-color: #f1f5f9 !important;
        color: #64748b !important;
        border: 1px solid #cbd5e1 !important;
        font-weight: 500 !important;
    }
    button[kind="secondary"]:hover,
    button[data-testid="baseButton-secondary"]:hover,
    div[data-testid="stButton"] button[kind="secondary"]:hover,
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background-color: #e2e8f0 !important;
        color: #1e293b !important;
        border-color: #94a3b8 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] button {
        padding: 5px 8px !important;
        font-size: 0.86em !important;
        white-space: nowrap !important;
    }
    input[type="radio"] {
        accent-color: #1e3a8a !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 9. サイドバー操作パネル（３日間／７日間 ＆ カレンダー ＆ 免責事項・お問い合わせ）
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定")

    # --- 1. 表示モード切り替え（元のトグル復帰：公式発表のみ青色ONで開始、ニュースは灰色OFF） ---
    st.write("**1. 表示モード切り替え**")
    btn_type_off = "primary" if st.session_state.show_official else "secondary"
    btn_type_news = "primary" if st.session_state.show_news else "secondary"

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if st.button("📢 公式発表", key="btn_mode_official", type=btn_type_off, use_container_width=True):
            st.session_state.show_official = not st.session_state.show_official
            if not st.session_state.show_official and not st.session_state.show_news:
                st.session_state.show_official = True
            st.rerun()
    with col_m2:
        if st.button("📰 ニュース", key="btn_mode_news", type=btn_type_news, use_container_width=True):
            st.session_state.show_news = not st.session_state.show_news
            if not st.session_state.show_official and not st.session_state.show_news:
                st.session_state.show_official = True
            st.rerun()

    st.markdown("---")

    # --- 2. 対象期間（３日間／７日間 ＆ カレンダー入力：公式・ニュース共通適用） ---
    st.write("**2. 対象期間**")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        type_p3 = "primary" if st.session_state.period_days == 3 else "secondary"
        if st.button("📅 3日間", key="btn_p_3", type=type_p3, use_container_width=True):
            st.session_state.period_days = 3
            st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
            st.rerun()
    with p_col2:
        type_p7 = "primary" if st.session_state.period_days == 7 else "secondary"
        if st.button("📅 7日間", key="btn_p_7", type=type_p7, use_container_width=True):
            st.session_state.period_days = 7
            st.session_state.custom_date_range = (today - datetime.timedelta(days=6), today)
            st.rerun()

    # カレンダー入力（任意の日程指定）
    date_val = st.date_input(
        "📅 カレンダーで任意指定",
        value=st.session_state.custom_date_range,
        max_value=today,
    )
    if isinstance(date_val, (tuple, list)) and len(date_val) == 2:
        start_date, end_date = date_val
        st.session_state.custom_date_range = (start_date, end_date)
    elif isinstance(date_val, (tuple, list)) and len(date_val) == 1:
        start_date = end_date = date_val[0]
        st.session_state.custom_date_range = (start_date, end_date)
    else:
        start_date = end_date = date_val
        st.session_state.custom_date_range = (start_date, end_date)

    diff_days = (end_date - start_date).days + 1
    st.caption(f"📅 選択中: **{start_date.strftime('%Y/%m/%d')} 〜 {end_date.strftime('%Y/%m/%d')}** ({diff_days}日間)")

    if st.session_state.hidden_companies:
        if st.button("👁️ すべての会社の記事を再表示", use_container_width=True):
            st.session_state.hidden_companies.clear()
            st.rerun()

    st.markdown("---")
    st.write("**3. データ更新**")
    st.caption("※サーバー負荷軽減のため、取得結果は1時間自動記憶されます。")
    if st.button("🔄 キャッシュを破棄して最新取得", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_fetch_time = datetime.datetime.now(JST)
        st.rerun()

    # 診断ログパネル
    with st.expander("🔍 巡回診断ログ（検証・監視）"):
        if st.session_state.diag_logs:
            for cname, log in st.session_state.diag_logs.items():
                icon = "🟢" if log["status"] == "SUCCESS" else "🔴"
                st.write(f"**{icon} {cname}** - 公式取得: {log['success_count']}件")
                for u in log["tried_urls"]:
                    st.caption(f"・{u}")
        else:
            st.caption("巡回完了後にログが表示されます。")

    st.markdown("---")
    # ★ 免責事項・お問い合わせ（左側サイドバーのみに集約）
    st.caption(
        "**【免責事項】**\n"
        "本サイトは公開情報を自動収集・整理して表示する個人開発ツールです。各鉄道会社および関連企業とは一切関係ありません。情報の完全性・正確性を保証するものではありません。"
    )
    st.caption(
        "**【お問い合わせ】**\n"
        "近鉄グループホールディングス デジタル戦略部 中谷\n"
        "(h5-nakatani@rw.kintetsu.co.jp)"
    )

# ==========================================
# 10. データ巡回・取得実行
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

# 表示グループ（東京メトロ・大阪メトロ・海遊館なし）
jr_list = [COMPANY_POOL[cid] for cid in JR_ORDER]
private_list = [COMPANY_POOL[cid] for cid in PRIVATE_ORDER]
kintetsu_list = [COMPANY_POOL[cid] for cid in KINTETSU_ORDER]

render_groups = [
    ("jr", "JR", jr_list),
    ("private", "私鉄", private_list),
    ("kintetsu", "近鉄グループ", kintetsu_list),
]

# ==========================================
# 11. 会社選択ナビゲーションフォーム
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
        width: auto !important;
        min-width: 165px;
        white-space: nowrap !important;
        word-break: keep-all !important;
        font-weight: 800;
        font-size: 1.15em;
        line-height: 1.3;
        cursor: pointer !important;
        user-select: none;
        padding: 4px 8px;
        border-radius: 6px;
        transition: all 0.15s ease;
    }
    .slim-label:hover {
        background-color: rgba(30, 58, 138, 0.12);
        transform: translateY(-1px);
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
    .comp-chk {
        display: none !important;
    }
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
    .comp-chk:checked + .comp-label {
        background-color: #1e3a8a !important;
        color: #ffffff !important;
        border-color: #1e3a8a !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px rgba(30, 58, 138, 0.35) !important;
    }
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
            width: auto !important;
            min-width: unset;
            white-space: nowrap !important;
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
    💡 会社名を押した後に、『選択した会社の記事を表示する』ボタンを押すと、その会社の記事だけを表示することができます。基本は全て表示します。
  </div>
  <div class="slim-jump-container">
    <div class="slim-jump-row">
      <div class="slim-label label-jr" id="toggle-btn-jr" title="クリックでJR各社を一括選択/解除">🚆 JR</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(jr_list, 'jr', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-private" id="toggle-btn-private" title="クリックで私鉄各社を一括選択/解除">🚇 私鉄</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(private_list, 'private', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-kintetsu" id="toggle-btn-kintetsu" title="クリックで近鉄グループ各社を一括選択/解除">🏢 近鉄グループ</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(kintetsu_list, 'kintetsu', sel_set)}
      </div>
    </div>
  </div>
  <div class="filter-action-bar">
    <button type="submit" class="apply-filter-btn">選択した会社の記事を表示する</button>
    <a href="?reset=1" class="clear-filter-btn">🔄 選択を解除する</a>
  </div>
</form>
"""

st.markdown(jump_form_html, unsafe_allow_html=True)

components.html(
    """
    <script>
    (function() {
        function setupGroupToggles() {
            const doc = window.parent.document;
            if (!doc) return;

            const groups = [
                { id: 'toggle-btn-jr', prefix: 'chk-jr-' },
                { id: 'toggle-btn-private', prefix: 'chk-private-' },
                { id: 'toggle-btn-kintetsu', prefix: 'chk-kintetsu-' }
            ];

            groups.forEach(function(g) {
                const el = doc.getElementById(g.id);
                if (!el) return;
                if (el.dataset.toggleBound === 'true') return;
                el.dataset.toggleBound = 'true';

                el.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();

                    const inputs = doc.querySelectorAll('input[id^="' + g.prefix + '"]');
                    if (!inputs || inputs.length === 0) return;

                    let allChecked = true;
                    inputs.forEach(function(inp) {
                        if (!inp.checked) allChecked = false;
                    });

                    const newChecked = !allChecked;
                    inputs.forEach(function(inp) {
                        inp.checked = newChecked;
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                });
            });
        }

        setupGroupToggles();
        let count = 0;
        const timer = setInterval(function() {
            setupGroupToggles();
            count++;
            if (count > 25) clearInterval(timer);
        }, 200);

        try {
            const observer = new MutationObserver(function() {
                setupGroupToggles();
            });
            if (window.parent && window.parent.document && window.parent.document.body) {
                observer.observe(window.parent.document.body, { childList: true, subtree: true });
            }
        } catch(err) {}
    })();
    </script>
    """,
    height=0,
    width=0,
)

# ==========================================
# 12. 結果の描画（トグル連動表示）
# ==========================================
for group_prefix, group_title, comp_list in render_groups:
    st.write("<br>", unsafe_allow_html=True)
    st.markdown(f"<div id='sec-{group_prefix}' style='scroll-margin-top: 15px;'></div>", unsafe_allow_html=True)
    st.markdown(f"## 【 {group_title} 】")
    st.divider()

    for comp in comp_list:
        raw_items = all_cached_data.get(comp["name"], [])

        # 指定期間内の抽出
        period_items = [
            item for item in raw_items
            if start_date <= item["date"] <= end_date
        ]

        official_items = [i for i in period_items if i["type"] == "公式発表"]
        general_items = [i for i in period_items if i["type"] == "ニュース（一般サイト）"]

        official_items.sort(key=lambda x: x["date"], reverse=True)
        general_items.sort(key=lambda x: x["date"], reverse=True)

        display_items = []
        if st.session_state.show_official:
            display_items.extend(official_items)
        if st.session_state.show_news:
            display_items.extend(general_items)

        # 公式HPリンク先はトップページ（top_url）を確実に参照
        main_url = comp.get("top_url", comp["urls"][0])
        anchor_id = f"{group_prefix}-{comp['id']}"

        is_manually_hidden = comp["id"] in st.session_state.hidden_companies
        is_filtered_out = has_filter and (comp["id"] not in st.session_state.selected_filter_companies)
        should_hide_articles = is_manually_hidden or is_filtered_out

        h_col1, h_col2 = st.columns([5, 1.3])
        with h_col1:
            st.markdown(
                f"""
                <div id='{anchor_id}' style='margin-top: 18px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 3px solid #1e3a8a; display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px;'>
                    <span style='font-size: 1.85em; font-weight: 800; color: #1e293b; line-height: 1.2;'>🏢 {comp['name']}</span>
                    <a href='{main_url}' target='_blank' rel='noreferrer noopener' style='font-size: 0.9em; font-weight: 600; color: #1e3a8a; text-decoration: none;'>[公式HP ↗]</a>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col2:
            st.write("<div style='margin-top: 22px;'></div>", unsafe_allow_html=True)
            btn_label = "記事を表示" if should_hide_articles else "記事を非表示"
            btn_type = "primary" if should_hide_articles else "secondary"
            if st.button(btn_label, key=f"btn_toggle_{group_prefix}_{comp['id']}", type=btn_type, use_container_width=True):
                if should_hide_articles:
                    if comp["id"] in st.session_state.hidden_companies:
                        st.session_state.hidden_companies.remove(comp["id"])
                    if has_filter and comp["id"] not in st.session_state.selected_filter_companies:
                        st.session_state.selected_filter_companies.add(comp["id"])
                else:
                    st.session_state.hidden_companies.add(comp["id"])
                    if comp["id"] in st.session_state.selected_filter_companies:
                        st.session_state.selected_filter_companies.remove(comp["id"])
                st.rerun()

        if should_hide_articles:
            st.write("")
            continue

        if not display_items:
            labels = []
            if st.session_state.show_official:
                labels.append("公式発表")
            if st.session_state.show_news:
                labels.append("ニュース")
            mode_str = "・".join(labels) if labels else "記事"
            st.info(f"📅 指定期間内の **{mode_str}** は **なし** です。")
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

                    title_link = item["url"]
                    if comp["id"] == "jr-west":
                        if item.get("pdf_url"):
                            action_link = item["pdf_url"]
                            action_caption = "掲載資料（PDF）を開く ↗"
                            file_badge = "🟥 **[PDF資料]**"
                        else:
                            action_link = item["url"]
                            action_caption = "掲載ページを開く ↗"
                            file_badge = "🌐 **[Web発表]**"
                    else:
                        action_link = item.get("pdf_url") or item["url"]
                        action_caption = "掲載資料（PDF）を開く ↗" if item.get("is_pdf") else "掲載ページを開く ↗"
                        file_badge = "🟥 **[PDF資料]**" if item.get("is_pdf") else "🌐 **[Web発表]**"

                else:
                    type_badge = (
                        "<div style='display:inline-block; padding:3px 9px; background-color:#f1f5f9; "
                        "color:#475569; font-size:0.78em; font-weight:600; border-radius:5px; "
                        "border:1px solid #cbd5e1; margin-bottom:4px;'>📰 ニュース（一般）</div>"
                    )
                    title_link = item["url"]
                    action_link = item["url"]
                    action_caption = "掲載ページを開く ↗"
                    file_badge = "🌐 **[Webニュース]**"

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge, unsafe_allow_html=True)
                        st.markdown(file_badge)
                        st.caption(f"情報元: {item['source']}")
                    with col_right:
                        st.markdown(
                            f"##### <a href='{title_link}' target='_blank' rel='noreferrer noopener'>{item['title']}</a>",
                            unsafe_allow_html=True,
                        )

                        if not is_official and item.get("summary"):
                            st.write(f"**主な内容:** {item['summary']}")

                        st.markdown(
                            f"<a href='{action_link}' target='_blank' rel='noreferrer noopener' class='link-action-btn'>🔗 {action_caption}</a>",
                            unsafe_allow_html=True,
                        )
            st.write("")
