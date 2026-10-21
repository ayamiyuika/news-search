import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil import parser
import requests

# 鉄道会社の定義（東から西へ順序付け）
RAILWAY_COMPANIES = [
    # --- JR各社（東から順） ---
    {
        "category": "JR",
        "name": "JR北海道",
        "order": 1,
        "url": "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
    },
    {
        "category": "JR",
        "name": "JR東日本",
        "order": 2,
        "url": "https://www.jreast.co.jp/company/",
    },
    {
        "category": "JR",
        "name": "JR東海",
        "order": 3,
        "url": "https://jr-central.co.jp/",
    },
    {
        "category": "JR",
        "name": "JR西日本",
        "order": 4,
        "url": "https://www.westjr.co.jp/press/",
    },
    {
        "category": "JR",
        "name": "JR四国",
        "order": 5,
        "url": "https://www.jr-shikoku.co.jp/03_news/press/",
    },
    {
        "category": "JR",
        "name": "JR九州",
        "order": 6,
        "url": "https://www.jrkyushu.co.jp/news/release/index.html",
    },
    # --- 私鉄各社（東から順：関東・中京・関西・九州） ---
    {
        "category": "私鉄（メトロ含む）",
        "name": "東武鉄道",
        "order": 101,
        "url": "https://www.tobu.co.jp/newsrelease/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京成電鉄",
        "order": 102,
        "url": "https://www.keisei.co.jp/keisei/kouhou/news/index.php",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東京メトロ",
        "order": 103,
        "url": "https://www.tokyometro.jp/news/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西武鉄道",
        "order": 104,
        "url": "https://www.seiburailway.jp/newsroom/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京王電鉄",
        "order": 105,
        "url": "https://www.keio.co.jp/news/update/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "小田急電鉄",
        "order": 106,
        "url": "https://www.odakyu.jp/company/about/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東急電鉄",
        "order": 107,
        "url": "https://www.tokyu.co.jp/information/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京浜急行電鉄",
        "order": 108,
        "url": "https://www.keikyu.co.jp/company/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "相模鉄道",
        "order": 109,
        "url": "https://www.sotetsu.co.jp/pressrelease/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "名古屋鉄道",
        "order": 110,
        "url": "https://www.meitetsu.co.jp/profile/news/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "近畿日本鉄道",
        "order": 111,
        "url": "https://www.kintetsu.co.jp/all_news/whatsnew.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京阪電気鉄道",
        "order": 112,
        "url": "https://www.keihan.co.jp/corporate/release/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "南海電気鉄道",
        "order": 113,
        "url": "https://www.nankai.co.jp/news.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪神電気鉄道",
        "order": 114,
        "url": "https://www.hanshin.co.jp/company/press/",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪急電鉄",
        "order": 115,
        "url": "https://www.hankyu.co.jp/company/news/index.html",
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西日本鉄道",
        "order": 116,
        "url": "https://www.nishitetsu.co.jp/release/",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_company_releases(company, days_back=7):
    """各社の発表一覧ページから直近X日以内の発表を収集（汎用パーサー）"""
    items = []
    base_url = company["url"]
    now = datetime.datetime.now()
    cutoff_date = (now - datetime.timedelta(days=days_back)).date()

    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=10)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        # リンク付きのテキストブロックを広く探索
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            href = urljoin(base_url, a_tag["href"])

            if not text or len(text) < 5:
                continue

            # 親・祖父母要素から日付テキストを探す
            parent = a_tag.find_parent(["li", "tr", "div", "dd", "article"])
            if not parent:
                continue

            full_block_text = parent.get_text(separator=" ", strip=True)

            # 日付解析の試行（202x年xx月xx日 / 202x.xx.xx 等）
            release_date = None
            for token in full_block_text.split():
                clean_token = (
                    token.replace("年", "/")
                    .replace("月", "/")
                    .replace("日", "")
                    .replace(".", "/")
                )
                try:
                    parsed_d = parser.parse(clean_token, fuzzy=False).date()
                    if cutoff_date <= parsed_d <= now.date():
                        release_date = parsed_d
                        break
                except Exception:
                    continue

            if release_date:
                # PDF判定
                is_pdf = (
                    href.lower().endswith(".pdf")
                    or "pdf" in full_block_text.lower()
                )
                # 種別判定（URLやテキストにnews/pressが含まれるか）
                doc_type = (
                    "広報発表"
                    if "release" in href.lower() or "press" in href.lower()
                    else "ニュース"
                )

                items.append({
                    "category": company["category"],
                    "order": company["order"],
                    "company": company["name"],
                    "date": release_date,
                    "title": text,
                    "type": doc_type,
                    "summary": full_block_text[:120] + "...",
                    "url": href,
                    "is_pdf": is_pdf,
                })

    except Exception as e:
        print(f"Error fetching {company['name']}: {e}")

    return items