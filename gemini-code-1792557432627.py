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

NAV_EXCLUDE_WORDS = {
    "キャラクター", "インスタ映え", "アトラクション", "関連事業", "採用情報", "リンク集",
    "会社概要", "経営理念", "企業情報", "サイトマップ", "プライバシーポリシー", "アクセス",
    "お問い合わせ",
