from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


OUTPUT = Path("/Users/jackshi/Desktop/GenAI_Project/Presentation_Speaker_Notes.docx")


SLIDES = [
    {
        "title": "Slide 1 - Project Overview",
        "timing": "Estimated speaking time: 1-1.5 minutes",
        "cue": "Flow: Start with how people really shop, introduce the experience, and end with what makes the project different.",
        "paragraphs": [
            "Think about how people actually shop online. We rarely start with a perfect search. We might begin with, \"I need a backpack,\" and then add, \"under fifty dollars,\" \"something blue,\" or \"not black.\" Most search engines treat those as separate searches. Our assistant treats them as one conversation.",
            "The user can speak or type naturally. The assistant remembers preferences across turns, asks a follow-up only when an important detail is missing, and recognizes when the user has moved on to a different product.",
            "It searches both our private Amazon catalog and live shopping results. The interface can show up to six product cards with images, prices, source labels, and retailer links. Users can also add products to a cart and see the estimated total.",
            "The important part is that the language model is not simply guessing what might be a good product. Every displayed recommendation must come from evidence the system actually found. The spoken recommendation also refers to the same product shown as the top card.",
            "We built the experience with LiveKit, LangGraph, Chroma, MCP, Serper Shopping, and the OpenAI API. Now let's look at what happens behind the scenes.",
        ],
    },
    {
        "title": "Slide 2 - How the Assistant Works",
        "timing": "Estimated speaking time: 1-1.5 minutes",
        "cue": "Flow: Carry the backpack example through voice capture, planning, both search tools, matching, and the final response.",
        "paragraphs": [
            "Let's follow one request through the system. Imagine the user says, \"Find me a blue backpack under fifty dollars, but not black.\"",
            "For a voice request, LiveKit captures the audio. Silero detects when the user has finished speaking, and OpenAI's gpt-realtime-whisper turns the speech into text. If the user types instead, the message can go directly into the shopping workflow.",
            "Inside LangGraph, the router identifies that the product is a backpack and saves the color, budget, and excluded color. These details stay in the shopping context, so the user can change them later without repeating everything.",
            "The planner decides whether we need the private catalog, live results, or both. Our MCP server exposes exactly two tools. rag.search searches a Chroma index containing 10,002 Amazon products. web.search uses Serper Shopping to collect current retailer evidence.",
            "The fifty-dollar limit becomes a numeric database filter. We do not ask semantic search to perform price math.",
            "The retriever compares the results, and the answerer selects the strongest supported match. Our demo uses OpenAI's gpt-5-mini for language decisions and tts-1 for speech. While the longer search runs, the assistant can speak a short progress message so the conversation does not go silent.",
            "But finding products is only half the problem. We also need to prove that the information is trustworthy.",
        ],
    },
    {
        "title": "Slide 3 - How Recommendations Stay Grounded",
        "timing": "Estimated speaking time: 1-1.5 minutes",
        "cue": "Flow: Explain why the two sources stay separate until the product identity is checked, then close on traceability.",
        "paragraphs": [
            "The main grounding challenge is making sure that facts from different sources actually belong to the same product.",
            "The private catalog gives us product facts, a catalog price, and a document ID. However, it is based on Amazon data from 2020, and it contains no ratings. That means the assistant is never allowed to invent a rating or present one as a catalog fact.",
            "Live Serper results can provide a newer price, delivery information, a rating when one is reported, and an external retailer link. These results may come from Amazon, Walmart, eBay, Target, and other approved retailers.",
            "We do not automatically combine two products just because their names look similar. The system checks the title along with details such as model, color, size, pack, and quantity. If those details conflict, the results remain separate.",
            "After those checks, the system creates one official top recommendation. In plain terms, that means the first card, explanation, citation, and spoken answer must all point to the same product.",
            "Every recommendation must trace back to either a private document ID or an approved retailer URL. We use a direct product link when one is available. Otherwise, we clearly label it as a retailer-search fallback. We do not scrape retailer pages.",
            "This structure lets the assistant feel conversational while keeping its product claims tied to real, visible evidence.",
        ],
    },
]


def xml_text(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def paragraph(text: str, style: str = "Normal", *, page_break_before: bool = False) -> str:
    page_break = '<w:pageBreakBefore/>' if page_break_before else ""
    preserve = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") else ""
    return (
        "<w:p>"
        f"<w:pPr><w:pStyle w:val=\"{style}\"/>{page_break}</w:pPr>"
        f"<w:r><w:t{preserve}>{xml_text(text)}</w:t></w:r>"
        "</w:p>"
    )


def page_field() -> str:
    return (
        "<w:p><w:pPr><w:jc w:val=\"right\"/></w:pPr>"
        "<w:r><w:rPr><w:color w:val=\"7A8793\"/><w:sz w:val=\"18\"/></w:rPr>"
        "<w:t>Page </w:t></w:r>"
        "<w:fldSimple w:instr=\"PAGE\"><w:r><w:rPr><w:color w:val=\"7A8793\"/>"
        "<w:sz w:val=\"18\"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple></w:p>"
    )


def make_document_xml() -> str:
    body = [
        paragraph("Presentation Speaker Notes", "DocTitle"),
        paragraph("Voice-to-Voice Product Discovery Assistant", "DocSubtitle"),
        paragraph("Jack | Austin | Ginger", "Metadata"),
        paragraph("Three-slide technical presentation | About 1-1.5 minutes per slide", "Metadata"),
    ]

    for index, slide in enumerate(SLIDES):
        body.append(paragraph(slide["title"], "Heading1", page_break_before=index > 0))
        body.append(paragraph(slide["timing"], "Metadata"))
        body.append(paragraph(slide["cue"], "DeliveryCue"))
        body.extend(paragraph(text) for text in slide["paragraphs"])

    body.append(
        "<w:sectPr>"
        '<w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )


STYLES_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="2B2B2B"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="0" w:after="120" w:line="300" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="2B2B2B"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DocTitle">
    <w:name w:val="Document Title"/><w:basedOn w:val="Normal"/><w:next w:val="DocSubtitle"/><w:qFormat/>
    <w:pPr><w:spacing w:before="0" w:after="100"/><w:keepNext/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="0B2545"/><w:sz w:val="48"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DocSubtitle">
    <w:name w:val="Document Subtitle"/><w:basedOn w:val="Normal"/><w:next w:val="Metadata"/>
    <w:pPr><w:spacing w:before="0" w:after="180"/><w:keepNext/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="5F6B76"/><w:sz w:val="25"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Metadata"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="360" w:after="200"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="280" w:after="140"/><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="2E74B5"/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="2"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="1F4D78"/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Metadata">
    <w:name w:val="Metadata"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="80" w:line="280" w:lineRule="auto"/><w:keepNext/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="6A7480"/><w:sz w:val="20"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DeliveryCue">
    <w:name w:val="Delivery Cue"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="80" w:after="180" w:line="280" w:lineRule="auto"/><w:keepNext/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:i/><w:color w:val="1F4D78"/><w:sz w:val="20"/></w:rPr>
  </w:style>
</w:styles>'''


CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''


PACKAGE_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


DOCUMENT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>'''


HEADER_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:color w:val="7A8793"/><w:sz w:val="18"/></w:rPr><w:t>VOICE-TO-VOICE PRODUCT DISCOVERY ASSISTANT</w:t></w:r></w:p>
</w:hdr>'''


SETTINGS_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/><w:updateFields w:val="true"/>
</w:settings>'''


APP_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application><Pages>3</Pages><Words>0</Words><Paragraphs>0</Paragraphs>
</Properties>'''


def core_xml() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Presentation Speaker Notes</dc:title><dc:subject>Voice-to-Voice Product Discovery Assistant</dc:subject>
  <dc:creator>Jack, Austin, and Ginger</dc:creator><cp:lastModifiedBy>Jack</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''


def build() -> None:
    OUTPUT.unlink(missing_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", CONTENT_TYPES)
        docx.writestr("_rels/.rels", PACKAGE_RELS)
        docx.writestr("docProps/core.xml", core_xml())
        docx.writestr("docProps/app.xml", APP_XML)
        docx.writestr("word/document.xml", make_document_xml())
        docx.writestr("word/styles.xml", STYLES_XML)
        docx.writestr("word/settings.xml", SETTINGS_XML)
        docx.writestr("word/header1.xml", HEADER_XML)
        docx.writestr("word/footer1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' + page_field() + '</w:ftr>')
        docx.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)


if __name__ == "__main__":
    build()
    print(OUTPUT)
