import re


def c_replace(html=""):
    """Clean HTML content"""
    if isinstance(html, str):
        html = html.replace("&gt;", ">")
        html = html.replace("&lt;", "<")
        html = html.replace("&amp;", "&")
        html = html.replace("&nbsp;", " ")
        html = html.replace("\r\n", " ")
        html = html.replace("\t", " ")
        html = html.replace("\n", " ")
        html = html.replace("\r", " ")
        html = html.replace("<p>", " ")
        html = html.replace("</p>", " ")
        html = html.replace("<ul>", " ")
        html = html.replace("</ul>", " ")
        html = html.replace("/<ul>", " ")
        html = html.replace("<li>", " ")
        html = html.replace("</li>", " ")
        html = html.replace("™", "")
        html = html.replace("​", "")

        html = re.sub(
            r"\* style specs start[^>]*>([\w\W]*?)style specs end \*", " ", html
        )
        html = re.sub(r"<script[^>]*>([\w\W]*?)</script>", " ", html)
        html = re.sub(r"<style[^>]*>([\w\W]*?)</style>", " ", html)
        html = re.sub(r"<!--([\w\W]*?)-->", " ", html)
        html = re.sub(r"<([\w\W]*?)>", " ", html)
        html = re.sub(r"<.*?>", " ", html)
        html = re.sub(r" +", " ", html)

        return html.strip()

    elif isinstance(html, list):
        return [j for j in [c_replace(i) for i in html] if j]

    else:
        raise TypeError(
            f"must be str or list - object pass is ({type(html)}) object...."
        )