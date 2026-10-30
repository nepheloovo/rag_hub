"""网页导入：抓取网页正文转 Markdown，作为文档走常规解析入库

安全：只允许 http/https；拒绝解析到内网 / 回环 / 链路本地地址的主机（防 SSRF）；限制大小与超时。
"""
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 15
SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"}
BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "br", "table", "ul", "ol", "blockquote", "pre"}
HEADINGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}


class WebImportError(ValueError):
    pass


class _MarkdownExtractor(HTMLParser):
    """极简 HTML → Markdown：保留标题层级、段落与列表，丢弃脚本样式和导航"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False
        self._heading = ""

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in HEADINGS and not self._skip:
            self._heading = HEADINGS[tag]
            self.parts.append(f"\n\n{self._heading} ")
        elif tag == "li" and not self._skip:
            self.parts.append("\n- ")
        elif tag in BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in HEADINGS:
            self._heading = ""
            self.parts.append("\n\n")
        elif tag in BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
            return
        if self._skip:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.parts.append(text)

    def markdown(self) -> str:
        text = "".join(self.parts)
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line not in ("-",))
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def _check_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebImportError(f"只支持 http/https 网址：{url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise WebImportError(f"无法解析域名：{parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebImportError(f"出于安全考虑，不允许抓取内网地址：{parsed.hostname}")


def html_to_markdown(html: str) -> tuple[str, str]:
    parser = _MarkdownExtractor()
    parser.feed(html)
    return parser.title, parser.markdown()


def fetch_markdown(url: str) -> tuple[str, str]:
    """返回 (标题, Markdown 正文)；重定向的每一跳都做内网校验"""
    current = url.strip()
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "ZhishuKnowledgeBot/1.0"}) as client:
        for _ in range(5):
            _check_host(current)
            resp = client.get(current)
            if resp.is_redirect and resp.headers.get("location"):
                current = str(resp.url.join(resp.headers["location"]))
                continue
            break
        else:
            raise WebImportError("重定向次数过多")
        if resp.status_code >= 400:
            raise WebImportError(f"抓取失败：HTTP {resp.status_code}")
        if len(resp.content) > MAX_BYTES:
            raise WebImportError("网页超过 5MB 上限")
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise WebImportError(f"不是网页内容：{content_type or '未知类型'}")
        text = resp.text
    if "html" in content_type:
        title, markdown = html_to_markdown(text)
    else:
        title, markdown = "", text.strip()
    if len(markdown) < 20:
        raise WebImportError("没有抓取到正文内容")
    title = title or urlparse(current).path.strip("/").split("/")[-1] or urlparse(current).hostname or "网页"
    return title, f"# {title}\n\n来源：{current}\n\n{markdown}"
