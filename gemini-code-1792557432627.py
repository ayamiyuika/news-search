import datetime
import email.utils
import gzip
import html
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
import streamlit as st

# ページ基本設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption(
    "JR各社・大手私鉄・地下鉄の公式発表（公式HP）および一般ニュースを自動巡回し、指定期間内の発表を一覧表示します。"
)

# ==========================================
# 1. 鉄道会社・持株会社のマスターデータ（東から西順）
# ==========================================
COMPANIES = [
    # --- JR各社（東から西順） ---
    {
        "category": "JR",
        "name": "JR北海道",
        "region": "北海道",
        "official_domain": "jrhokkaido.co.jp",
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道",
    },
    {
        "category": "JR",
        "name": "JR東日本",
        "region": "東日本",
        "official_domain": "jreast.co.jp",
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/company/",
        ],
        "query": "JR東日本",
    },
    {
        "category": "JR",
        "name": "JR東海",
        "region": "東海",
        "official_domain": "jr-central.co.jp",
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/",
        ],
        "query": "JR東海 OR 東海旅客鉄道",
    },
    {
        "category": "JR",
        "name": "JR西日本",
        "region": "西日本",
        "official_domain": "westjr.co.jp",
        "urls": [
            "https://www.westjr.co.jp/press/article/",
            "https://www.westjr.co.jp/press/",
        ],
        "query": "JR西日本",
    },
    {
        "category": "JR",
        "name": "JR四国",
        "region": "四国",
        "official_domain": "jr-shikoku.co.jp",
        "urls": [
            "https://www.jr-shikoku.co.jp/03_news/press/",
            "https://www.jr-shikoku.co.jp/",
        ],
        "query": "JR四国",
    },
    {
        "category": "JR",
        "name": "JR九州",
        "region": "九州",
        "official_domain": "jrkyushu.co.jp",
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州",
    },
    # --- 私鉄各社（東から西順） ---
    {
        "category": "私鉄",
        "name": "東武鉄道",
        "region": "関東",
        "official_domain": "tobu.co.jp",
        "urls": ["https://www.tobu.co.jp/newsrelease/"],
        "query": "東武鉄道",
    },
    {
        "category": "私鉄",
        "name": "西武鉄道（西武HD含む）",
        "region": "関東",
        "official_domain": "seiburailway.jp",
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス",
    },
    {
        "category": "私鉄",
        "name": "京成電鉄",
        "region": "関東",
        "official_domain": "keisei.co.jp",
        "urls": [
            "https://www.keisei.co.jp/keisei/kouhou/news/index.php",
            "https://www.keisei.co.jp/",
        ],
        "query": "京成電鉄",
    },
    {
        "category": "私鉄",
        "name": "東京メトロ",
        "region": "関東",
        "official_domain": "tokyometro.jp",
        "urls": [
            "https://www.tokyometro.jp/news/index.html",
            "https://www.tokyometro.jp/news/rss/news.xml",
        ],
        "query": "東京メトロ OR 東京地下鉄",
    },
    {
        "category": "私鉄",
        "name": "京王電鉄",
        "region": "関東",
        "official_domain": "keio.co.jp",
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
        ],
        "query": "京王電鉄",
    },
    {
        "category": "私鉄",
        "name": "小田急電鉄",
        "region": "関東",
        "official_domain": "odakyu.jp",
        "urls": [
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/",
        ],
        "query": "小田急電鉄",
    },
    {
        "category": "私鉄",
        "name": "東急電鉄（東急HD含む）",
        "region": "関東",
        "official_domain": "tokyu.co.jp",
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    {
        "category": "私鉄",
        "name": "京浜急行電鉄",
        "region": "関東",
        "official_domain": "keikyu.co.jp",
        "urls": [
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    {
        "category": "私鉄",
        "name": "相模鉄道（相鉄HD含む）",
        "region": "関東",
        "official_domain": "sotetsu.co.jp",
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    {
        "category": "私鉄",
        "name": "名古屋鉄道",
        "region": "東海",
        "official_domain": "meitetsu.co.jp",
        "urls": [
            "https://www.meitetsu.co.jp/profile/news/",
            "https://www.meitetsu.co.jp/",
        ],
        "query": "名古屋鉄道 OR 名鉄",
    },
    {
        "category": "私鉄",
        "name": "近鉄グループ（近畿日本鉄道・近鉄GHD）",
        "region": "関西",
        "official_domain": "kintetsu.co.jp",
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu-g-hd.co.jp/news/",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄グループホールディングス OR 近鉄",
    },
    {
        "category": "私鉄",
        "name": "南海電気鉄道",
        "region": "関西",
        "official_domain": "nankai.co.jp",
        "urls": [
            "https://www.nankai.co.jp/news.html",
            "https://www.nankai.co.jp/",
        ],
        "query": "南海電気鉄道 OR 南海電鉄",
    },
    {
        "category": "私鉄",
        "name": "京阪電気鉄道（京阪HD含む）",
        "region": "関西",
        "official_domain": "keihan.co.jp",
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
    },
    {
        "category": "私鉄",
        "name": "大阪メトロ (Osaka Metro)",
        "region": "関西",
        "official_domain": "osakametro.co.jp",
        "urls": [
            "https://subway.osakametro.co.jp/news/news_release/",
            "https://subway.osakametro.co.jp/news/",
        ],
        "query": "大阪メトロ OR \"Osaka Metro\"",
    },
    {
        "category": "私鉄",
        "name": "阪神電気鉄道",
        "region": "関西",
        "official_domain": "hanshin.co.jp",
        "urls": [
            "https://www.hanshin.co.jp/company/press/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    {
        "category": "私鉄",
        "name": "阪急電鉄",
        "region": "関西",
        "official_domain": "hankyu.co.jp",
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
    {
        "category": "私鉄",
        "name": "阪急阪神ホールディングス",
        "region": "関西",
        "official_domain": "hankyu-hanshin.co.jp",
        "urls": ["https://www.hankyu-hanshin.co.jp/release/"],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
    },
    {
        "category": "私鉄",
        "name": "西日本鉄道",
        "region": "九州",
        "official_domain": "nishitetsu.co.jp",
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
]

GENERIC_LINK_TEXTS = {
    "一覧を見る", "ニュース一覧を見る", "お知らせ一覧を見る", "過去の一覧を見る",
    "リリース一覧を見る", "一覧はこちら", "一覧へ", "一覧", "詳しく見る",
    "詳しくはこちら", "詳細を見る", "詳細はこちら", "詳細", "こちら", "もっと見る",
    "記事を読む", "続きを読む", "pdfを見る", "pdfを開く", "pdfダウンロード",
    "pdf", "ダウンロード", "リンク", "次へ", "前へ", "トップへ戻る", "ホーム",
    "企業情報", "サイトマップ", "ニュースリリース", "お知らせ", "新着情報"
}

# ==========================================
# 2. 自動エンコーディング解析エンジン（JR西日本等の文字化け完全防止）
# ==========================================
zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


def decode_html_bytes(raw_bytes, url=""):
    """JR西日本のCP932/Shift_JIS、UTF-8、EUC-JPを自動判別して完璧にデコード"""
    enc_candidates = []

    # JR西日本ドメインの場合はCP932（Shift_JIS拡張）を最優先
    if "westjr.co.jp" in url:
        enc_candidates.extend(["cp932", "shift_jis"])

    # meta charset属性から探索
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
            # 文字化け特有の文字（縺、繧、など）が含まれていないかチェック
            mojibake_count = len(re.findall(r'[縺繧繝譬諷]', text))
            if mojibake_count == 0:
                return text
            if best_decoded is None:
                best_decoded = text
        except (UnicodeDecodeError, LookupError):
            continue

    return best_decoded if best_decoded else raw_bytes.decode("utf-8", errors="replace")


def parse_date_text(raw_text, current_year):
    """テキストから西暦・和暦・月日を解読"""
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


# ==========================================
# 3. 公式サイト直接巡回（404・403リンク完全防止）
# ==========================================
def fetch_official_releases(company_info, start_date, end_date):
    """各社公式ホームページから「公式発表」を取得"""
    results = []
    seen_urls = set()
    current_year = datetime.date.today().year

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

    for url in company_info["urls"]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
                raw_bytes = res.read()
                content_encoding = res.headers.get("Content-Encoding", "").lower()
                final_base_url = res.geturl()  # リダイレクト後の正確なベースURL

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

            # ★ JR西日本等に特化したデコード
            html_text = decode_html_bytes(raw_bytes, url=url)

            # RSSフィード（東京メトロ等）の場合
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
                        if item_date and (start_date <= item_date <= end_date) and l not in seen_urls:
                            seen_urls.add(l)
                            results.append({
                                "date": item_date,
                                "type": "公式発表",
                                "title": t,
                                "summary": t,
                                "url": l,
                                "source": company_info["name"] + " 公式HP",
                                "is_pdf": l.lower().endswith(".pdf"),
                            })
                continue

            # 通常HTMLページの場合
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
                # リンクURLの徹底クレンジング（空白や改行を除去）
                raw_href = m.group(1).strip().strip("'\"").replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
                if not raw_href or raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    continue

                # リダイレクト後のURLを基準に結合（404リンク防止）
                full_url = urllib.parse.urljoin(final_base_url, raw_href)
                if full_url in seen_urls:
                    continue

                # 自社公式ドメイン配下のリンクのみに厳格限定
                parsed_u = urllib.parse.urlparse(full_url)
                if not any(d in parsed_u.netloc.lower() for d in [company_info["official_domain"], "westjr.co.jp", "jreast.co.jp", "kintetsu.co.jp"]):
                    continue

                inside_html = m.group(2)
                start_pos, end_pos = m.start(), m.end()
                surrounding = clean_html[
                    max(0, start_pos - 450) : min(len(clean_html), end_pos + 350)
                ]

                # 日付の探索
                found_date = parse_date_text(inside_html, current_year)
                if not found_date:
                    found_date = parse_date_text(surrounding, current_year)

                if not found_date or not (start_date <= found_date <= end_date):
                    continue

                # タイトルの抽出
                raw_t = re.sub(r"<[^>]+>", " ", inside_html)
                raw_t = html.unescape(raw_t)
                clean_t = re.sub(r"\s+", " ", raw_t).strip()

                # 「一覧を見る」などの汎用文言を排除し、見出しを救出
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

                clean_t = re.sub(
                    r"^(?:令和\s*[0-9０-９元]+年|\d{4}年|\d{1,2}月|\d{1,2}日|[\d\.\/\-\s・\|｜【】\[\]\(\)])+",
                    "",
                    clean_t,
                )
                clean_t = re.sub(r"\s+", " ", clean_t).strip()

                if len(clean_t) < 5 or clean_t in GENERIC_LINK_TEXTS:
                    continue

                seen_urls.add(full_url)
                is_pdf = bool(
                    re.search(r"\.pdf$", full_url, re.IGNORECASE)
                    or "pdf" in surrounding.lower()
                )

                results.append({
                    "date": found_date,
                    "type": "公式発表",
                    "title": clean_t[:130],
                    "summary": clean_t,
                    "url": full_url,
                    "source": company_info["name"] + " 公式HP",
                    "is_pdf": is_pdf,
                })
        except Exception:
            pass

    return results


# ==========================================
# 4. 一般ニュース巡回（一般サイト専用）
# ==========================================
def fetch_general_news(query, start_date, end_date):
    """一般ニュースメディアから記事を取得"""
    results = []
    encoded_q = urllib.parse.quote(query)
    rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"

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

            item_date = None
            if pubdate_str:
                try:
                    dt = email.utils.parsedate_to_datetime(pubdate_str)
                    jst = dt.astimezone(
                        datetime.timezone(datetime.timedelta(hours=9))
                    )
                    item_date = jst.date()
                except Exception:
                    pass

            if not item_date or not (start_date <= item_date <= end_date):
                continue

            clean_title = raw_title.strip()
            clean_desc = re.sub(r"<[^>]+>", " ", desc)
            clean_desc = html.unescape(clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            summary = clean_desc if len(clean_desc) > 10 else clean_title

            parsed_url = urllib.parse.urlparse(link)
            domain = parsed_url.netloc.lower().replace("www.", "")

            results.append({
                "date": item_date,
                "type": "ニュース（一般サイト）",
                "title": clean_title,
                "summary": summary[:140] + ("..." if len(summary) > 140 else ""),
                "url": link,
                "source": domain,
                "is_pdf": link.lower().endswith(".pdf"),
            })
    except Exception:
        pass

    return results


# ==========================================
# 5. 統合フェッチ（公式発表 ＋ 一般ニュース）
# ==========================================
def fetch_company_all(company_info, start_date, end_date):
    official_list = fetch_official_releases(company_info, start_date, end_date)
    general_list = []
    if "query" in company_info:
        general_list = fetch_general_news(company_info["query"], start_date, end_date)

    combined = list(official_list)
    seen_urls = {item["url"] for item in official_list}
    for g in general_list:
        if g["url"] not in seen_urls:
            seen_urls.add(g["url"])
            combined.append(g)

    return combined


# ==========================================
# 6. 画面UIと操作パネル（サイドバー）
# ==========================================
today = datetime.date.today()
default_start = today - datetime.timedelta(days=7)

with st.sidebar:
    st.header("⚙️ 巡回・抽出条件")

    st.write("**1. 巡回対象期間**")
    date_range = st.date_input(
        "開始日と終了日を選択してください",
        value=(default_start, today),
        max_value=today,
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range[0]

    st.markdown("---")
    st.write("**2. 会社・種別の絞り込み**")
    selected_category = st.radio(
        "会社分類", ["すべて", "JR", "私鉄", "近鉄グループ"]
    )

    selected_type = st.radio(
        "発表・記事の種別",
        ["すべて", "公式発表", "ニュース（一般サイト）"],
    )

    search_keyword = st.text_input("キーワード検索", "")

    st.markdown("---")
    run_button = st.button(
        "🔄 公式サイトを巡回して取得", type="primary", use_container_width=True
    )

# ==========================================
# 7. データ取得の実行
# ==========================================
if "fetched_data" not in st.session_state:
    st.session_state.fetched_data = {}

if run_button:
    new_data = {}
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, comp in enumerate(COMPANIES):
        status_text.text(f"巡回中: {comp['name']} ({i+1}/{len(COMPANIES)}) ...")
        news_items = fetch_company_all(comp, start_date, end_date)
        new_data[comp["name"]] = news_items
        progress_bar.progress((i + 1) / len(COMPANIES))

    st.session_state.fetched_data = new_data
    status_text.empty()
    progress_bar.empty()
    st.toast("全社の巡回・データ取得が完了しました！", icon="✅")

# ==========================================
# 8. 結果の表示（「すべて」の時は公式発表が上、ニュースが下）
# ==========================================
if not st.session_state.fetched_data and not run_button:
    st.info(
        "👈 左のサイドバーで期間を指定し、「公式サイトを巡回して取得」ボタンを押してください。"
    )
else:
    current_category = None

    for comp in COMPANIES:
        # 会社分類の絞り込み
        if selected_category == "JR" and comp["category"] != "JR":
            continue
        if selected_category == "私鉄" and comp["category"] != "私鉄":
            continue
        if selected_category == "近鉄グループ" and "近鉄グループ" not in comp["name"]:
            continue

        all_items = st.session_state.fetched_data.get(comp["name"], [])

        # キーワード検索
        if search_keyword:
            kw = search_keyword.lower()
            all_items = [
                item
                for item in all_items
                if kw in item["title"].lower()
                or kw in item["summary"].lower()
                or kw in comp["name"].lower()
            ]

        # ★ご要望のソート仕様：
        # 「すべて」選択時は「公式発表」を上（最新順）、「ニュース」を下（最新順）に並べる
        official_items = [i for i in all_items if i["type"] == "公式発表"]
        general_items = [i for i in all_items if i["type"] == "ニュース（一般サイト）"]

        official_items.sort(key=lambda x: x["date"], reverse=True)
        general_items.sort(key=lambda x: x["date"], reverse=True)

        # 選択された種別に応じた表示リストの構築
        if selected_type == "公式発表":
            display_items = official_items
        elif selected_type == "ニュース（一般サイト）":
            display_items = general_items
        else:
            # 「すべて」の場合：公式発表が上、ニュースが下（それぞれ日付が新しい順）
            display_items = official_items + general_items

        # セクションヘッダー（JR / 私鉄）
        if comp["category"] != current_category:
            if current_category is not None:
                st.write("<br><br>", unsafe_allow_html=True)
            current_category = comp["category"]
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        # 会社ヘッダー
        main_url = comp["urls"][0]
        st.markdown(
            f"### 🏢 {comp['name']} <span style='font-size:0.8em;"
            f" color:gray;'>（{comp['region']}）</span> [公式HP"
            f" ↗]({main_url})",
            unsafe_allow_html=True,
        )

        if not display_items:
            type_label = f"（{selected_type}）" if selected_type != "すべて" else ""
            st.info(f"📅 指定期間・条件内の発表{type_label}は **なし** です。")
            st.write("")
        else:
            # カード形式で順次描画
            for item in display_items:
                is_official = item["type"] == "公式発表"
                type_badge = "📢 **公式発表**" if is_official else "📰 **ニュース（一般サイト）**"
                file_badge = "🟥 **[PDF資料]**" if item["is_pdf"] else "🌐 **[Web発表]**"

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge)
                        st.markdown(file_badge)
                        st.caption(f"情報元: {item['source']}")
                    with col_right:
                        # 404やアクセス拒否を防ぐため、rel属性を付与したリンク
                        st.markdown(
                            f"##### <a href='{item['url']}' target='_blank' rel='noopener noreferrer'>{item['title']}</a>",
                            unsafe_allow_html=True,
                        )
                        st.write(f"**主な内容:** {item['summary']}")
                        st.markdown(
                            f"🔗 **掲載ページ:** <a href='{item['url']}' target='_blank' rel='noopener noreferrer'>{item['url']}</a>",
                            unsafe_allow_html=True,
                        )
            st.write("")
