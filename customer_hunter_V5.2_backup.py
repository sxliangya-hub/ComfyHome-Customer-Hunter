import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pandas as pd
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# COMFYHOME CUSTOMER HUNTER V5.2
# Multi-language B2B customer discovery for:
# Pajama / Sleepwear / Robe / Loungewear / Blanket
#
# Languages:
# English / Spanish / Portuguese / German /
# French / Italian / Dutch
#
# V5.2 improvements:
# 1. Country detection prioritizes ccTLD/domain
# 2. Better Portuguese vs Spanish separation
# 3. Anti-bot / verification-page detection
# 4. B2B signals separated from generic retail signals
# 5. Evidence-based scoring with confidence fields
# 6. Safer keyword matching to reduce false positives
# ============================================================


PAGE_TIMEOUT = 30000
MAX_INTERNAL_PAGES = 15
DELAY_BETWEEN_SITES = 2
DELAY_BETWEEN_PAGES = 0.8
MIN_REAL_CONTENT_CHARS = 180


# ============================================================
# PRODUCT KEYWORDS
# ============================================================

PRODUCT_KEYWORDS = {
    "Pajama": [
        "pajama", "pajamas", "pyjama", "pyjamas",
        "pijama", "pijamas",
        "schlafanzug", "schlafanzüge", "schlafanzuege",
        "pigiama", "pigiami",
        "pyjama's",
    ],
    "Sleepwear": [
        "sleepwear", "nightwear",
        "ropa de dormir", "ropa para dormir", "ropa de noche",
        "roupa de dormir", "roupa para dormir", "roupa de noite",
        "nachtwäsche", "nachtwaesche", "schlafbekleidung",
        "vêtements de nuit", "vetements de nuit", "tenue de nuit",
        "abbigliamento da notte", "indumenti da notte",
        "nachtkleding", "nachtmode",
    ],
    "Robe": [
        "bathrobe", "dressing gown", "housecoat",
        "bata de baño", "bata de casa", "albornoz",
        "roupão", "roupao", "robe de chambre",
        "bademantel", "morgenmantel",
        "peignoir", "peignoir de bain",
        "accappatoio", "vestaglia",
        "badjas", "ochtendjas",
    ],
    "Loungewear": [
        "loungewear", "homewear",
        "ropa de estar en casa", "ropa de casa", "ropa cómoda",
        "roupa de ficar em casa", "roupa de casa", "roupa confortável",
        "freizeitkleidung", "hauskleidung",
        "vêtements d'intérieur", "vetements d'interieur",
        "tenue d'intérieur", "tenue d'interieur",
        "abbigliamento da casa",
        "huiskleding",
    ],
    "Blanket": [
        "blanket", "throw blanket", "fleece blanket", "sherpa blanket",
        "manta", "manta de sofá", "manta de sofa", "manta polar", "cobija",
        "cobertor", "manta de sofá", "manta de sofa",
        "decke", "kuscheldecke", "flauschdecke", "wohndecke",
        "couverture", "plaid", "couverture polaire",
        "coperta", "coperta in pile",
        "deken", "fleece deken",
    ],
}


# ============================================================
# BUSINESS TYPE SIGNALS
# Strong signals first; generic retail signals are deliberately
# weaker so ordinary B2C stores are not over-rated.
# ============================================================

BUSINESS_TYPES = {
    "Wholesale": [
        "wholesale", "wholesaler", "wholesale supplier",
        "mayorista", "mayoristas", "venta al por mayor", "ventas al por mayor",
        "atacado", "atacadista", "venda por atacado", "vendas por atacado",
        "großhandel", "grosshandel", "großhändler", "grosshaendler",
        "grossiste", "grossistes", "vente en gros",
        "grossista", "grossisti", "vendita all'ingrosso",
        "groothandel", "groothandelaar",
    ],
    "Importer": [
        "importer", "importing", "import",
        "importador", "importadora", "importadores", "importación", "importacion",
        "importador", "importadora", "importadores", "importação", "importacao",
        "importeur", "importeure",
        "importateur", "importateurs",
        "importatore", "importatori",
    ],
    "Distributor": [
        "distributor", "distribution",
        "distribuidor", "distribuidora", "distribución", "distribucion",
        "distribuidor", "distribuidora", "distribuição", "distribuicao",
        "vertrieb", "distributor",
        "distributeur", "distribution",
        "distributore", "distribuzione",
        "distributeur", "distributie",
    ],
    "Supermarket": [
        "supermarket", "hypermarket", "grocery",
        "supermercado", "hipermercado",
        "supermarkt", "lebensmittelmarkt",
        "supermarché", "supermarche", "hypermarché", "hypermarche",
        "supermercato", "ipermercato",
        "supermarkt", "hypermarkt",
    ],
    "Department Store": [
        "department store", "grandes almacenes",
        "loja de departamentos", "warenhaus", "kaufhaus",
        "grand magasin", "grande magazzino", "warenhuis",
    ],
    "Fashion Brand": [
        "fashion brand", "clothing brand", "fashion label",
        "marca de moda", "marca de ropa",
        "marca de moda", "marca de roupa",
        "modemarke", "bekleidungsmarke",
        "marque de mode", "marque de vêtements", "marque de vetements",
        "marchio di moda", "marca di abbigliamento",
        "modemerk", "kledingmerk",
    ],
    "Retailer": [
        "retailer", "retail store", "online store", "shop online",
        "minorista", "tienda online", "tienda en línea",
        "varejista", "loja online", "loja virtual",
        "einzelhandel", "einzelhändler", "einzelhaendler", "online shop",
        "détaillant", "detaillant", "boutique en ligne", "magasin",
        "rivenditore", "negozio online", "negozio",
        "detailhandel", "winkel", "webshop",
    ],
}


# ============================================================
# BUYER INTENT
# ============================================================

BUYER_INTENT_KEYWORDS = {
    "Wholesale": [
        "wholesale", "wholesaler",
        "venta al por mayor", "mayorista",
        "atacado", "atacadista",
        "großhandel", "grosshandel",
        "grossiste", "vente en gros",
        "grossista", "vendita all'ingrosso",
        "groothandel",
    ],
    "OEM": [
        "oem", "fabricación oem", "fabricacion oem",
        "produção oem", "producao oem",
        "oem herstellung", "fabrication oem",
        "produzione oem",
    ],
    "ODM": [
        "odm", "product development", "desarrollo de productos",
        "desenvolvimento de produtos", "produktentwicklung",
        "développement de produits", "developpement de produits",
        "sviluppo prodotto", "productontwikkeling",
    ],
    "Private Label": [
        "private label", "private-label",
        "marca privada", "marca propia",
        "marca própria", "marca propria",
        "eigenmarke", "marque privée", "marque privee",
        "marchio privato", "eigen merk",
    ],
    "Sourcing": [
        "sourcing", "product sourcing", "supplier sourcing",
        "abastecimiento", "aprovisionamiento",
        "sourcing de produtos", "abastecimento",
        "beschaffung", "produktbeschaffung",
        "approvisionnement", "approvvigionamento", "inkoop",
    ],
    "Import": [
        "import", "importer", "importing",
        "importación", "importacion", "importador",
        "importação", "importacao", "importador",
        "importeur", "importateur", "importatore",
    ],
    "Supplier": [
        "supplier", "suppliers",
        "proveedor", "proveedores",
        "fornecedor", "fornecedores",
        "lieferant", "lieferanten",
        "fournisseur", "fournisseurs",
        "fornitore", "fornitori",
        "leverancier", "leveranciers",
    ],
    "Bulk Order": [
        "bulk order", "bulk orders", "large quantity", "large quantities",
        "pedido al por mayor", "grandes cantidades",
        "pedido em grande quantidade", "grandes quantidades",
        "große mengen", "grosse mengen", "großbestellung", "grossbestellung",
        "commande en gros", "grandes quantités", "grandes quantites",
        "ordine all'ingrosso", "grandi quantità", "grandi quantita",
        "grote hoeveelheden", "grote bestelling",
    ],
}


# ============================================================
# STRONG B2B SIGNALS
# ============================================================

STRONG_B2B_SIGNALS = [
    # English
    "wholesale", "wholesaler", "trade buyer", "bulk order",
    "minimum order", "minimum order quantity", "moq",
    "private label", "own brand", "sourcing",
    "importer", "distributor",

    # Spanish
    "mayorista", "mayoristas", "venta al por mayor",
    "comprar al por mayor", "compra al por mayor",
    "pedido mínimo", "pedido minimo", "cantidad mínima", "cantidad minima",
    "marca propia", "marca privada", "distribuidor", "importador",
    "revendedor", "revendedores",

    # Portuguese
    "atacado", "atacadista", "venda por atacado", "vendas por atacado",
    "compra no atacado", "compras no atacado",
    "pedido mínimo", "pedido minimo", "quantidade mínima", "quantidade minima",
    "marca própria", "marca propria", "revenda", "revendedor", "revendedores",
    "distribuidor", "importador", "direto da fábrica", "direto da fabrica",
    "fabricação própria", "fabricacao propria",

    # German
    "großhandel", "grosshandel", "großhändler", "grosshaendler",
    "mindestbestellmenge", "mindestbestellung", "händler",
    "haendler", "eigenmarke", "importeur", "vertrieb",

    # French
    "grossiste", "grossistes", "vente en gros",
    "quantité minimale", "quantite minimale", "commande minimum",
    "marque propre", "distributeur", "importateur",

    # Italian
    "grossista", "grossisti", "vendita all'ingrosso",
    "quantità minima", "quantita minima", "ordine minimo",
    "marchio privato", "distributore", "importatore",

    # Dutch
    "groothandel", "groothandelaar", "minimale bestelhoeveelheid",
    "minimum bestelling", "eigen merk", "importeur", "distributeur",
]


# ============================================================
# LANGUAGE SIGNALS
# Generic shared words such as "pijama" are NOT enough.
# ============================================================

LANGUAGE_STRONG = {
    "Portuguese": [
        "português", "portugues", "brasil", "brasileiro", "brasileira",
        "atacado", "atacadista", "revenda", "revendedor", "revendedores",
        "roupão", "roupao", "fabricação própria", "fabricacao propria",
        "direto da fábrica", "direto da fabrica",
        "fornecedor", "fornecedores", "loja", "loja online",
        "distribuidor", "importador", "compras", "produtos", "contato",
        "pedido mínimo", "pedido minimo",
    ],
    "Spanish": [
        "español", "espanol", "españa", "espana", "española",
        "mayorista", "mayoristas", "venta al por mayor",
        "revendedor", "revendedores", "importador", "importadores",
        "tienda", "tienda online", "proveedor", "proveedores",
        "distribuidor", "productos", "contacto", "compras",
        "pedido mínimo", "pedido minimo",
    ],
    "German": [
        "deutsch", "deutschland", "schlafanzug", "bademantel",
        "großhandel", "grosshandel", "großhändler", "grosshaendler",
        "lieferant", "lieferanten", "bestellung", "produkte", "kontakt",
        "nachtwäsche", "nachtwaesche",
    ],
    "French": [
        "français", "francais", "france", "grossiste", "grossistes",
        "vente en gros", "distributeur", "importateur",
        "fournisseur", "fournisseurs", "produits", "commande",
        "peignoir", "couverture",
    ],
    "Italian": [
        "italiano", "italia", "grossista", "grossisti",
        "vendita all'ingrosso", "distributore", "importatore",
        "fornitore", "fornitori", "prodotti", "contatti", "ordine",
        "pigiama", "accappatoio",
    ],
    "Dutch": [
        "nederlands", "nederland", "groothandel", "groothandelaar",
        "distributeur", "importeur", "leverancier", "leveranciers",
        "producten", "contact", "bestelling", "badjas", "deken",
    ],
    "English": [
        "wholesale", "wholesaler", "distributor", "importer", "supplier",
        "sleepwear", "bathrobe", "dressing gown", "blanket",
        "contact us", "about us", "shop now",
    ],
}


# ============================================================
# COUNTRY / DOMAIN
# ============================================================

DOMAIN_COUNTRY = {
    ".com.br": "Brazil",
    ".br": "Brazil",
    ".com.mx": "Mexico",
    ".mx": "Mexico",
    ".com.ar": "Argentina",
    ".ar": "Argentina",
    ".com.cl": "Chile",
    ".cl": "Chile",
    ".com.co": "Colombia",
    ".co": "Colombia",
    ".pe": "Peru",
    ".es": "Spain",
    ".pt": "Portugal",
    ".de": "Germany",
    ".fr": "France",
    ".it": "Italy",
    ".nl": "Netherlands",
    ".be": "Belgium",
    ".at": "Austria",
    ".ch": "Switzerland",
    ".co.uk": "United Kingdom",
    ".uk": "United Kingdom",
    ".us": "United States",
    ".ca": "Canada",
    ".au": "Australia",
    ".za": "South Africa",
}


COUNTRY_KEYWORDS = {
    "Brazil": ["brasil", "brazil", "brasileiro", "brasileira", "brl"],
    "Portugal": ["portugal", "português", "portugues"],
    "Spain": ["españa", "espana", "español", "espanol", "spanish"],
    "Mexico": ["méxico", "mexico", "mexican", "mxn"],
    "Argentina": ["argentina", "argentinian", "ars"],
    "Chile": ["chile", "chilean", "clp"],
    "Colombia": ["colombia", "colombiano", "cop"],
    "Peru": ["peru", "perú", "pen"],
    "Germany": ["germany", "deutschland", "german"],
    "France": ["france", "français", "francais", "french"],
    "Italy": ["italia", "italy", "italian"],
    "Netherlands": ["netherlands", "nederland", "dutch"],
    "Belgium": ["belgium", "belgië", "belgie", "belgian"],
    "Austria": ["austria", "österreich", "osterreich"],
    "Switzerland": ["switzerland", "schweiz", "suisse", "svizzera"],
    "United Kingdom": ["united kingdom", "england", "scotland", "wales"],
    "United States": ["united states", "usa", "american"],
    "Canada": ["canada", "canadian"],
    "Australia": ["australia", "australian"],
    "South Africa": ["south africa", "south african"],
}


# ============================================================
# ACCESS / BOT CHECK
# ============================================================

BLOCK_PAGE_PHRASES = [
    "verificando acesso",
    "verifique seu acesso",
    "verificando o acesso",
    "checking your browser",
    "checking your browser before accessing",
    "verify you are human",
    "verify your access",
    "access denied",
    "access verification",
    "just a moment",
    "cloudflare",
    "enable javascript",
    "please enable javascript",
    "security check",
    "bot detection",
    "captcha",
    "are you human",
    "checking if the site connection is secure",
    "ray id",
]


# ============================================================
# HELPERS
# ============================================================

def normalize_text(text):
    text = text or ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def folded(text):
    """Lowercase + accent-insensitive copy for matching."""
    text = normalize_text(text).lower()
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def phrase_present(text, phrase):
    """
    Safer matching:
    - phrases are searched as phrases
    - single words use word boundaries
    This reduces false positives such as 'robe' inside another word.
    """
    t = folded(text)
    p = folded(phrase).strip()
    if not p:
        return False
    if " " in p or "'" in p or "-" in p:
        return p in t
    return re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", t) is not None


def count_phrase_hits(text, keywords):
    hits = []
    for keyword in keywords:
        if phrase_present(text, keyword):
            hits.append(keyword)
    return sorted(set(hits))


def normalize_url(url):
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def normalize_domain(url):
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def same_domain(base_url, target_url):
    return normalize_domain(base_url) == normalize_domain(target_url)


def detect_access_problem(text):
    t = folded(text)
    hits = [p for p in BLOCK_PAGE_PHRASES if folded(p) in t]

    if not hits:
        if len(normalize_text(text)) < MIN_REAL_CONTENT_CHARS:
            return "EMPTY_CONTENT"
        return "REAL_CONTENT"

    if any(x in t for x in [
        "verificando acesso",
        "verifique seu acesso",
        "verificando o acesso",
        "checking your browser",
        "verify you are human",
        "just a moment",
    ]):
        return "BOT_CHECK"

    if "cloudflare" in t:
        return "CLOUDFLARE"

    if "captcha" in t:
        return "CAPTCHA"

    if "access denied" in t:
        return "ACCESS_DENIED"

    return "ACCESS_BLOCKED"


def get_country_from_domain(url):
    host = normalize_domain(url)
    for suffix in sorted(DOMAIN_COUNTRY, key=len, reverse=True):
        if host.endswith(suffix):
            return DOMAIN_COUNTRY[suffix]
    return "Unknown"


# ============================================================
# LANGUAGE
# ============================================================

def detect_language(text, url=""):
    scores = {k: 0 for k in LANGUAGE_STRONG}

    for language, keywords in LANGUAGE_STRONG.items():
        hits = count_phrase_hits(text, keywords)
        # Each strong hit = 3, but cap text-only language score
        scores[language] += min(len(hits) * 3, 24)

    t = folded(text)

    # Portuguese-specific orthographic signals
    pt_signals = [
        "não", "você", "vocês", "ção", "ções", "ã", "õ",
        "atacado", "roupao", "fornecedor", "revenda",
    ]
    for s in pt_signals:
        if folded(s) in t:
            scores["Portuguese"] += 2

    # Spanish-specific signals
    es_signals = [
        "ñ", "¿", "¡", "también", "usted", "ustedes",
        "mayorista", "al por mayor", "proveedor",
    ]
    for s in es_signals:
        if folded(s) in t:
            scores["Spanish"] += 2

    # Domain is a strong supporting signal, not the only language signal.
    country = get_country_from_domain(url)
    if country == "Brazil":
        scores["Portuguese"] += 12
    elif country == "Portugal":
        scores["Portuguese"] += 12
    elif country == "Spain":
        scores["Spanish"] += 12
    elif country == "Germany":
        scores["German"] += 12
    elif country == "France":
        scores["French"] += 12
    elif country == "Italy":
        scores["Italian"] += 12
    elif country == "Netherlands":
        scores["Dutch"] += 12
    elif country == "United Kingdom" or country == "United States":
        scores["English"] += 8

    # "pijama" is shared by Portuguese and Spanish.
    # It gets no language points by itself.
    if "pijama" in t:
        if any(x in t for x in [
            "atacado", "atacadista", "revenda", "roupao",
            "fornecedor", "fabrica", "brasil", "loja",
        ]):
            scores["Portuguese"] += 8

        if any(x in t for x in [
            "mayorista", "al por mayor", "revendedor",
            "proveedor", "tienda", "españa", "espana",
        ]):
            scores["Spanish"] += 8

    best = max(scores, key=scores.get)
    best_score = scores[best]
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

    if best_score == 0:
        return "Unknown", 0, 0

    # Confidence based on score and separation from second-best language.
    margin = best_score - second_score
    if best_score >= 18 and margin >= 6:
        confidence = 95
    elif best_score >= 12 and margin >= 4:
        confidence = 85
    elif best_score >= 8 and margin >= 3:
        confidence = 70
    else:
        confidence = 55

    return best, best_score, confidence


# ============================================================
# PRODUCTS
# ============================================================

def detect_products(text):
    results = {}
    for category, keywords in PRODUCT_KEYWORDS.items():
        hits = count_phrase_hits(text, keywords)
        if hits:
            results[category] = hits
    return results


# ============================================================
# BUSINESS TYPE
# ============================================================

def detect_business_type(text):
    scores = {}
    evidence = {}

    for business_type, keywords in BUSINESS_TYPES.items():
        hits = count_phrase_hits(text, keywords)
        if hits:
            evidence[business_type] = hits
            # Strong business types get more weight.
            if business_type in ("Wholesale", "Importer", "Distributor"):
                scores[business_type] = min(len(hits) * 4, 20)
            else:
                scores[business_type] = min(len(hits) * 2, 10)

    if not scores:
        return "Unknown", [], 0

    best = max(scores, key=scores.get)
    best_score = scores[best]
    total = sum(scores.values())
    confidence = min(95, 45 + int((best_score / max(total, 1)) * 50))

    return best, evidence.get(best, []), confidence


# ============================================================
# BUYER INTENT
# ============================================================

def detect_buyer_intent(text):
    found = []
    evidence = {}

    for intent, keywords in BUYER_INTENT_KEYWORDS.items():
        hits = count_phrase_hits(text, keywords)
        if hits:
            found.append(intent)
            evidence[intent] = hits

    return found, evidence


# ============================================================
# COUNTRY
# ============================================================

def detect_country(text, url):
    domain_country = get_country_from_domain(url)

    if domain_country != "Unknown":
        return domain_country, 98, "DOMAIN"

    scores = {}
    for country, keywords in COUNTRY_KEYWORDS.items():
        hits = count_phrase_hits(text, keywords)
        if hits:
            scores[country] = len(hits)

    if not scores:
        return "Unknown", 0, "NONE"

    best = max(scores, key=scores.get)
    best_score = scores[best]
    second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0

    if best_score >= 3 and best_score > second:
        confidence = 80
    elif best_score >= 2 and best_score > second:
        confidence = 65
    else:
        confidence = 45

    return best, confidence, "TEXT"


# ============================================================
# CONTACT EXTRACTION
# ============================================================

def extract_emails(text):
    pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    emails = re.findall(pattern, text or "")

    excluded = [
        "example.com", "sentry.io", "wixpress.com",
        "schema.org", "cloudflare.com",
    ]

    results = []
    for email in emails:
        email = email.strip()
        if any(x in email.lower() for x in excluded):
            continue
        if email.lower() not in {x.lower() for x in results}:
            results.append(email)

    return results[:10]


def extract_phones(text):
    # General international phone pattern. It intentionally avoids
    # trying to decide whether every number is a phone.
    pattern = r"""
        (?:
            \+\d{1,3}[\s().-]?
        )?
        (?:\(?\d{2,5}\)?[\s.-]?)?
        \d{3,4}[\s.-]?\d{3,4}
    """

    matches = re.findall(pattern, text or "", re.VERBOSE)
    results = []

    for phone in matches:
        phone = re.sub(r"\s+", " ", phone).strip()
        digits = re.sub(r"\D", "", phone)

        if 7 <= len(digits) <= 15 and phone not in results:
            results.append(phone)

    return results[:10]


# ============================================================
# SCORING
# ============================================================

def calculate_customer_score(
    products,
    business_type,
    buyer_intent,
    emails,
    phones,
    text,
    access_status,
):
    # Maximum conceptual score = 100.
    # Product fit: 30
    # B2B business model: 30
    # Buyer intent: 25
    # Contact/evidence: 15

    score = 0

    # -------------------------
    # Product relevance (30)
    # -------------------------
    product_points = {
        "Pajama": 25,
        "Sleepwear": 22,
        "Robe": 20,
        "Loungewear": 18,
        "Blanket": 18,
    }

    product_hits = 0
    for product in products:
        if product in product_points:
            score += product_points[product]
            product_hits += 1

    if product_hits > 1:
        score += min((product_hits - 1) * 3, 5)

    score = min(score, 30)

    # -------------------------
    # B2B business model (30)
    # -------------------------
    business_points = {
        "Wholesale": 30,
        "Importer": 30,
        "Distributor": 28,
        "Supermarket": 22,
        "Department Store": 22,
        "Fashion Brand": 20,
        "Retailer": 10,
        "Unknown": 0,
    }

    score += business_points.get(business_type, 0)

    # -------------------------
    # Buyer intent (25)
    # -------------------------
    intent_points = {
        "Wholesale": 10,
        "Private Label": 8,
        "Sourcing": 8,
        "Import": 8,
        "OEM": 6,
        "ODM": 5,
        "Bulk Order": 8,
        "Supplier": 2,
    }

    intent_score = sum(intent_points.get(x, 0) for x in buyer_intent)
    score += min(intent_score, 25)

    # -------------------------
    # Direct B2B evidence bonus
    # -------------------------
    strong_hits = count_phrase_hits(text, STRONG_B2B_SIGNALS)
    score += min(len(strong_hits) * 2, 10)

    # -------------------------
    # Contact evidence
    # -------------------------
    if emails:
        score += 6
    if phones:
        score += 4

    # -------------------------
    # Access quality
    # -------------------------
    if access_status != "REAL_CONTENT":
        # Do not pretend a blocked site is a low-value customer.
        # Its score is simply not reliable.
        return 0, strong_hits

    return min(score, 100), strong_hits


def get_grade(score, access_status="REAL_CONTENT"):
    if access_status != "REAL_CONTENT":
        return "N/A"
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 50:
        return "B"
    if score >= 30:
        return "C"
    return "D"


def get_buyer_level(score, buyer_intent, business_type, access_status):
    if access_status != "REAL_CONTENT":
        return "UNVERIFIED"

    high_intent = any(
        x in buyer_intent
        for x in [
            "Wholesale", "Sourcing", "Import",
            "Private Label", "OEM", "ODM", "Bulk Order",
        ]
    )

    strong_business = business_type in {
        "Wholesale", "Importer", "Distributor",
        "Supermarket", "Department Store",
    }

    if score >= 85 and (high_intent or strong_business):
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    return "LOW"


# ============================================================
# INTERNAL LINK DISCOVERY
# ============================================================

IMPORTANT_LINK_WORDS = [
    # English
    "contact", "about", "wholesale", "products", "collections",
    "trade", "business", "catalog", "catalogue", "become a retailer",
    # Spanish
    "contacto", "nosotros", "mayorista", "productos", "colecciones",
    "distribuidor", "empresa", "catálogo", "catalogo",
    # Portuguese
    "contato", "sobre", "atacado", "produtos", "coleções", "colecoes",
    "distribuidor", "empresa", "catálogo", "catalogo", "revenda",
    # German
    "kontakt", "über uns", "ueber uns", "großhandel", "grosshandel",
    "produkte", "kollektionen", "händler", "haendler",
    # French
    "contact", "à propos", "a propos", "grossiste", "produits",
    "collections", "distributeur", "catalogue",
    # Italian
    "contatti", "chi siamo", "grossista", "prodotti", "collezioni",
    "distributore", "catalogo",
    # Dutch
    "contact", "over ons", "groothandel", "producten", "collecties",
    "distributeur", "catalogus",
]


def find_important_links(base_url, page):
    links = []
    try:
        anchors = page.locator("a").all()

        for anchor in anchors:
            try:
                href = anchor.get_attribute("href")
                if not href:
                    continue

                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                if parsed.scheme not in ("http", "https"):
                    continue
                if not same_domain(base_url, full_url):
                    continue

                link_text = ""
                try:
                    link_text = anchor.inner_text(timeout=1500).strip()
                except Exception:
                    pass

                combined = folded(link_text + " " + full_url)

                if any(folded(word) in combined for word in IMPORTANT_LINK_WORDS):
                    clean_url = full_url.split("#")[0]
                    if clean_url not in links:
                        links.append(clean_url)

            except Exception:
                continue

    except Exception:
        pass

    return links


# ============================================================
# PAGE TEXT
# ============================================================

def safe_body_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def get_company_name(page):
    try:
        name = page.locator(
            'meta[property="og:site_name"]'
        ).get_attribute("content")
        if name:
            return normalize_text(name)
    except Exception:
        pass

    try:
        title = page.title()
        if title:
            return normalize_text(title)
    except Exception:
        pass

    return ""


# ============================================================
# ANALYZE WEBSITE
# ============================================================

def analyze_website(browser, url, index, total):
    print()
    print("=" * 78)
    print(f"[{index}/{total}] {url}")

    result = {
        "Company Name": "",
        "Website": url,
        "Country": "Unknown",
        "Country Confidence": 0,
        "Country Source": "",
        "Language": "Unknown",
        "Language Confidence": 0,
        "Business Type": "Unknown",
        "Business Confidence": 0,
        "Buyer Intent": "",
        "Pajama": "",
        "Sleepwear": "",
        "Robe": "",
        "Loungewear": "",
        "Blanket": "",
        "Wholesale": "",
        "OEM": "",
        "ODM": "",
        "Private Label": "",
        "Sourcing": "",
        "Import": "",
        "Supplier": "",
        "Bulk Order": "",
        "Email": "",
        "Phone": "",
        "B2B Evidence": "",
        "Pages Crawled": 0,
        "Customer Score": 0,
        "Buyer Level": "UNVERIFIED",
        "Grade": "N/A",
        "Access Status": "",
        "Crawl Status": "",
        "Crawl Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Error": "",
    }

    page = None

    try:
        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0 Safari/537.36"
            ),
            locale="en-US",
        )

        # Helpful for modern websites.
        page.set_default_timeout(8000)

        print("打开网站...")

        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        if response:
            status = response.status
            print(f"HTTP Status: {status}")

            if status >= 400:
                result["Crawl Status"] = f"HTTP {status}"
                result["Error"] = f"HTTP status {status}"
                return result

        page.wait_for_timeout(2500)

        company_name = get_company_name(page)
        result["Company Name"] = company_name

        homepage_text = safe_body_text(page)
        access_status = detect_access_problem(homepage_text)
        result["Access Status"] = access_status

        # IMPORTANT:
        # A 200 response can still be a bot-check page.
        if access_status != "REAL_CONTENT":
            print(f"⚠️ 网站访问状态：{access_status}")
            result["Crawl Status"] = "UNVERIFIED"
            result["Error"] = (
                "The returned page appears to be a bot/verification "
                "or empty-content page. Customer score is not reliable."
            )
            return result

        all_text_parts = [homepage_text]
        visited_pages = [url]

        print("寻找多语言重要页面...")

        internal_links = find_important_links(url, page)
        internal_links = internal_links[:MAX_INTERNAL_PAGES]

        print(f"发现 {len(internal_links)} 个相关页面")

        for link in internal_links:
            if link in visited_pages:
                continue

            print(f"  → {link}")

            try:
                response = page.goto(
                    link,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                if response and response.status >= 400:
                    print(f"    HTTP {response.status}")
                    continue

                page.wait_for_timeout(int(DELAY_BETWEEN_PAGES * 1000))

                text = safe_body_text(page)
                page_access = detect_access_problem(text)

                if page_access != "REAL_CONTENT":
                    print(f"    跳过验证页面：{page_access}")
                    continue

                if text:
                    all_text_parts.append(text)
                    visited_pages.append(link)

            except PlaywrightTimeoutError:
                print("    页面超时")
            except Exception as e:
                print(f"    页面失败：{e}")

        all_text = normalize_text(" ".join(all_text_parts))
        result["Pages Crawled"] = len(visited_pages)

        # ====================================================
        # ANALYSIS
        # ====================================================

        language, language_score, language_conf = detect_language(
            all_text, url
        )
        country, country_conf, country_source = detect_country(
            all_text, url
        )
        products = detect_products(all_text)

        business_type, business_hits, business_conf = detect_business_type(
            all_text
        )
        buyer_intent, intent_evidence = detect_buyer_intent(all_text)

        emails = extract_emails(all_text)
        phones = extract_phones(all_text)

        score, b2b_hits = calculate_customer_score(
            products=products,
            business_type=business_type,
            buyer_intent=buyer_intent,
            emails=emails,
            phones=phones,
            text=all_text,
            access_status=access_status,
        )

        grade = get_grade(score, access_status)
        buyer_level = get_buyer_level(
            score,
            buyer_intent,
            business_type,
            access_status,
        )

        # ====================================================
        # SAVE
        # ====================================================

        result["Language"] = language
        result["Language Confidence"] = language_conf
        result["Country"] = country
        result["Country Confidence"] = country_conf
        result["Country Source"] = country_source
        result["Business Type"] = business_type
        result["Business Confidence"] = business_conf

        result["Buyer Intent"] = ", ".join(buyer_intent)

        for category in PRODUCT_KEYWORDS:
            if category in products:
                result[category] = "YES"

        for intent in [
            "Wholesale", "OEM", "ODM", "Private Label",
            "Sourcing", "Import", "Supplier", "Bulk Order",
        ]:
            if intent in buyer_intent:
                result[intent] = "YES"

        result["Email"] = "; ".join(emails)
        result["Phone"] = "; ".join(phones)
        result["B2B Evidence"] = "; ".join(b2b_hits[:15])

        result["Customer Score"] = score
        result["Buyer Level"] = buyer_level
        result["Grade"] = grade
        result["Crawl Status"] = "SUCCESS"

        # ====================================================
        # CONSOLE
        # ====================================================

        print()
        print(f"公司：{company_name}")
        print(f"语言：{language} ({language_conf}%)")
        print(f"国家：{country} ({country_conf}% / {country_source})")
        print(f"客户类型：{business_type}")
        print(
            "买家意向："
            + (", ".join(buyer_intent) if buyer_intent else "未发现")
        )
        print(
            "产品："
            + (", ".join(products.keys()) if products else "未发现")
        )
        print(f"Email：{result['Email'] or '未找到'}")
        print(f"Phone：{result['Phone'] or '未找到'}")
        print(f"B2B证据：{result['B2B Evidence'] or '未发现'}")
        print(f"评分：{score}/100")
        print(f"Buyer Level：{buyer_level}")
        print(f"Grade：{grade}")

        return result

    except PlaywrightTimeoutError:
        result["Crawl Status"] = "TIMEOUT"
        result["Error"] = "Website loading timeout"
        print("访问超时")
        return result

    except Exception as e:
        result["Crawl Status"] = "FAILED"
        result["Error"] = str(e)
        print(f"访问失败：{url}")
        print(f"原因：{e}")
        return result

    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


# ============================================================
# LOAD WEBSITES
# ============================================================

def load_websites(filename):
    websites = []

    try:
        with open(filename, "r", encoding="utf-8") as file:
            for line in file:
                url = line.strip()

                if not url or url.startswith("#"):
                    continue

                url = normalize_url(url)

                if url:
                    websites.append(url)

    except FileNotFoundError:
        print(f"找不到：{filename}")
        return []

    return list(dict.fromkeys(websites))


# ============================================================
# MAIN
# ============================================================

def main():
    websites = load_websites("customers.txt")

    if not websites:
        print("customers.txt 没有有效网站。")
        return

    print()
    print("=" * 78)
    print("COMFYHOME CUSTOMER HUNTER V5.2")
    print("MULTI-LANGUAGE B2B CUSTOMER ANALYZER")
    print("EN / ES / PT / DE / FR / IT / NL")
    print("=" * 78)
    print()
    print(f"待分析网站：{len(websites)}")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
        )

        total = len(websites)

        for index, url in enumerate(websites, start=1):
            result = analyze_website(
                browser,
                url,
                index,
                total,
            )

            results.append(result)

            if index < total:
                time.sleep(DELAY_BETWEEN_SITES)

        browser.close()

    # ========================================================
    # EXCEL
    # ========================================================

    df = pd.DataFrame(results)

    if not df.empty:
        df = df.sort_values(
            by=["Customer Score"],
            ascending=False,
        )

    output_file = (
        "ComfyHome_Customer_Leads_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".xlsx"
    )

    df.to_excel(
        output_file,
        index=False,
    )

    print()
    print("=" * 78)
    print("🎉 全部分析完成！")
    print("=" * 78)
    print()
    print(f"Excel：{output_file}")
    print()

    print("语言统计：")
    print(df["Language"].value_counts())
    print()

    print("国家统计：")
    print(df["Country"].value_counts())
    print()

    print("客户等级：")
    print(df["Grade"].value_counts())
    print()

    print("访问状态：")
    print(df["Access Status"].value_counts())
    print()

    print("S级客户：")

    s_clients = df[df["Grade"] == "S"]

    if s_clients.empty:
        print("  暂无 S 级客户")
    else:
        for _, row in s_clients.iterrows():
            print(
                f"  ★ {row['Company Name']} "
                f"| {row['Country']} "
                f"| {row['Language']} "
                f"| {row['Customer Score']}"
            )


if __name__ == "__main__":
    main()
