"""Rule-based tagging of jobs: experience level and job category.

Rules look at the title first (most reliable), then at experience requirements in the description.
They are heuristics: anything they can't place stays None ("not specified") rather than guessed.
"""
import html
import re

EXPERIENCE_LEVELS = ("intern", "fresher", "junior", "mid", "senior", "leadership")
EXPERIENCE_LABELS = {
    "intern": "Internship", "fresher": "Fresher / Entry level (0–1 yr)", "junior": "Junior (1–3 yrs)",
    "mid": "Mid level (3–6 yrs)", "senior": "Senior (6+ yrs)", "leadership": "Leadership",
}
# Levels a fresher can realistically apply to; used for the Telegram digest and dashboard shortcuts.
FRESHER_FRIENDLY = ("intern", "fresher", "junior")

CATEGORY_LABELS = {
    "software": "Software Development",
    "data_ai": "Data & AI",
    "devops_cloud": "Cloud & DevOps",
    "security": "Cybersecurity",
    "qa_testing": "QA & Testing",
    "hardware_embedded": "Hardware & Embedded",
    "networking": "Networking & Telecom",
    "it_support": "IT Support & Operations",
    "consulting_tech": "Tech Consulting & Enterprise Apps",
    "product_design": "Product & Design",
    "non_it": "Non-IT",
    "other": "Other / Unclassified",
}
IT_CATEGORIES = tuple(c for c in CATEGORY_LABELS if c not in ("non_it", "other"))


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)


# --- Experience -------------------------------------------------------------------------------------

_INTERN = _rx(r"\bintern(ship)?s?\b", r"\bco-?op\b", r"\bapprentice(ship)?\b", r"\bworking student\b",
              r"\bwerkstudent", r"\bstagiaire\b", r"\bpracticante\b", r"\bsummer (analyst|associate)\b", r"\b实习")
_LEADERSHIP = _rx(r"\bdirector\b", r"\bvice president\b", r"\bvp\b", r"\bhead of\b", r"\bchief\b",
                  r"\b(cto|cio|ciso|cfo|coo)\b", r"\bmanaging partner\b", r"\bgeneral manager\b")
_SENIOR = _rx(r"\bsenior\b", r"\bsr\b\.?", r"\bstaff\b", r"\bprincipal\b", r"\blead\b", r"\barchitect\b",
              r"\bmanager\b", r"\bdistinguished\b", r"\bfellow\b", r"(?-i:\b(III|IV|V)\b)", r"\bL[5-9]\b", r"\bexpert\b",
              r"\bspecialist (iii|3)\b", r"\b资深|高级")
_FRESHER = _rx(r"\bfreshers?\b", r"\bnew grad(uate)?s?\b", r"\bnew college grad", r"(?-i:\bNCG\b)", r"\bgraduate\b",
               r"\bgrad\b", r"\btrainee\b", r"\bentry[- ]level\b", r"\bcampus\b", r"\bearly[- ]career\b",
               r"\buniversity (hire|grad|recruit)", r"(?-i:\bGET\b)", r"\b(engineer|developer|analyst) (?-i:I|1)\b(?!\s*[I1])",
               r"\b校招|应届")
_HIRES_GRADUATES = _rx(r"\bmanager\b", r"\brecruit", r"\blead\b", r"\bdirector\b", r"\bhead\b", r"\bpartner\b",
                       r"\bcoordinator\b", r"\bprogram(me)? (manager|owner)\b", r"\btalent\b")
_JUNIOR = _rx(r"\bjunior\b", r"\bjr\b\.?", r"\bassociate\b", r"\b(engineer|developer|analyst|scientist) (?-i:II|2)\b")

_TAGS = re.compile(r"<[^>]+>")
_YEARS_RANGE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
_YEARS_MIN = re.compile(
    r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)(?:'s?)?\s+(?:of\s+)?(?:[\w/&,-]+\s+){0,5}?(?:experience|exp\b|work)", re.I)
_YEARS_PHRASE = re.compile(r"\b(?:minimum|at least|min\.?)\s+(?:of\s+)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
_FRESHER_TEXT = _rx(r"\bfreshers?\b", r"\bno (prior )?experience (is )?required\b", r"\b0\s*(?:-|to)\s*1\s*years?\b",
                    r"\brecent graduates?\b", r"\bgraduating (in|class of) 20\d\d\b", r"\b20\d\d (batch|pass[- ]?outs?)\b",
                    r"\bexperience level:\s*(freshers|graduates|entry)", r"\bnew grads?\b")


def plain_text(value: str | None, limit: int = 20000) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", value[:limit * 3])))[:limit]


def years_required(text: str) -> int | None:
    """Minimum years of experience asked for, from the first requirement mentioned (usually the basic one)."""
    candidates = []
    for pattern in (_YEARS_RANGE, _YEARS_PHRASE, _YEARS_MIN):
        match = pattern.search(text)
        if match:
            candidates.append((match.start(), int(match.group(1))))
    candidates = [(pos, years) for pos, years in candidates if years <= 25]
    return min(candidates)[1] if candidates else None


def level_from_years(years: int) -> str:
    if years <= 0:
        return "fresher"
    if years <= 2:
        return "junior"
    if years <= 5:
        return "mid"
    return "senior"


def classify_experience(title: str | None, description: str | None = None) -> tuple[str | None, int | None]:
    """(experience level or None, minimum years asked for or None)."""
    title = title or ""
    text = plain_text(description)
    years = years_required(text) if text else None
    if _INTERN.search(title):
        return "intern", years
    # "Graduate Staff", "Senior Trainee": an explicit entry-level word wins, except in roles that hire
    # graduates ("Campus Recruiting Manager", "Graduate Program Lead").
    if _FRESHER.search(title) and not _HIRES_GRADUATES.search(title):
        return "fresher", years
    if _LEADERSHIP.search(title):
        return "leadership", years
    if _SENIOR.search(title):
        return "senior", years
    if _FRESHER.search(title):
        return "fresher", years
    if _JUNIOR.search(title):
        return ("fresher" if years == 0 else "junior"), years
    if text and _FRESHER_TEXT.search(text) and (years is None or years <= 1):
        return "fresher", years
    if years is not None:
        return level_from_years(years), years
    return None, None


# --- Category ---------------------------------------------------------------------------------------

# Roles that are clearly not IT even when the title also contains a tech word ("Software Sales Executive").
_NON_IT_STRONG = _rx(
    r"\baccount (executive|manager|director)\b", r"\bsales (rep|representative|executive|manager|director|specialist|associate|lead)\b",
    r"\bbusiness development\b", r"\bmarketing\b", r"\brecruit(er|ing)\b", r"\btalent acquisition\b", r"\baccountant\b",
    r"\bparalegal\b", r"\b(legal )?counsel\b", r"\battorney\b", r"\blawyer\b", r"\bwarehouse\b", r"\bfulfil?ment (associate|center)\b",
    r"\bdriver\b", r"\bdelivery associate\b", r"\bnurse\b", r"\bpharmacist\b", r"\bcashier\b", r"\bsecurity (officer|guard)\b",
    r"\b(maintenance|hvac|installation|electrical|field service|mechanical) technician\b", r"\bmechanic\b", r"\belectrician\b",
    r"\b(mechanical|civil|chemical|structural|manufacturing|process|industrial) engineer", r"\bconstruction\b",
    r"\bpayroll\b", r"\bdata entry\b", r"\bbiller\b", r"\breceptionist\b", r"\bexecutive assistant\b", r"\badministrative assistant\b",
    r"\bcopywriter\b", r"\bpublic relations\b", r"\bevent (manager|coordinator)\b", r"\bchef\b", r"\bcook\b",
    r"\bcustomer service (representative|associate)\b", r"\bcall cent(er|re)\b", r"\btax (manager|senior|associate|consultant|analyst)\b",
    r"\baudit(or)?\b(?!.*\b(it|technology|cyber)\b)", r"\breal estate\b", r"\bprocurement\b", r"\bbuyer\b",
)
_CATEGORY_RULES = [
    ("hardware_embedded", _rx(
        r"\basic\b", r"\bfpga\b", r"\brtl\b", r"\bvlsi\b", r"\bsilicon\b", r"\bsoc (design|architect|verification|validation)", r"\bphysical design\b",
        r"\bdesign verification\b", r"\bdft\b", r"\banalog\b", r"\bmixed[- ]signal\b", r"\bfirmware\b", r"\bembedded\b",
        r"\bhardware\b", r"\bchip\b", r"\bsemiconductor\b", r"\bpcb\b", r"\bcircuit\b", r"\bsignal integrity\b",
        r"\belectrical engineer", r"\bpackaging engineer\b", r"\bvalidation engineer\b", r"\bpost[- ]silicon\b", r"\bgpu\b")),
    ("security", _rx(
        r"\bsecurity\b(?! (officer|guard))", r"\bcyber", r"\binfosec\b", r"\bsoc analyst\b", r"\bpenetration\b", r"\bpentest",
        r"\bappsec\b", r"\bidentity (and|&) access\b", r"\biam\b", r"\bthreat\b", r"\bvulnerability\b", r"\bsiem\b",
        r"\bgrc\b", r"\bforensic", r"\bsaviynt\b", r"\bsailpoint\b", r"\bokta\b", r"\bcryptograph")),
    ("data_ai", _rx(
        r"\bdata (scien|engineer|analy|architect|platform|warehouse|governance|modell?er|quality)", r"\bmachine learning\b",
        r"\bml\b", r"\bai\b", r"\bartificial intelligence\b", r"\bdeep learning\b", r"\bnlp\b", r"\bcomputer vision\b",
        r"\banalytics\b", r"\bbusiness intelligence\b", r"\bbi (developer|engineer|analyst)\b", r"\bbig data\b", r"\bllm",
        r"\bgen ?ai\b", r"\bgenerative\b", r"\bresearch scientist\b", r"\bapplied scientist\b", r"\bstatistic",
        r"\betl\b", r"\bdatabricks\b", r"\bsnowflake\b", r"\bpower ?bi\b", r"\btableau\b", r"\bdata\b(?! center)",
        r"\bagentic\b", r"\bperception\b", r"\brobotics\b", r"数据|算法|机器学习|人工智能|大模型")),
    ("devops_cloud", _rx(
        r"\bdevops\b", r"\bsre\b", r"\bsite reliability\b", r"\bcloud\b", r"\bplatform engineer", r"\binfrastructure\b",
        r"\bkubernetes\b", r"\baws\b", r"\bazure\b", r"\bgcp\b", r"\blinux\b", r"\bunix\b", r"\brelease engineer",
        r"\bbuild engineer", r"\bmlops\b", r"\bdevsecops\b", r"\bdata cent(er|re)\b", r"\bstorage engineer", r"\bvirtuali[sz]ation\b",
        r"\bsystems? engineer", r"\bproduction engineer", r"运维|云")),
    ("qa_testing", _rx(
        r"\bqa\b", r"\bquality assurance\b", r"\btest(ing)? (engineer|analyst|lead|manager|automation|specialist)",
        r"\btester\b", r"\bsdet\b", r"\bautomation test", r"\bsoftware test", r"\bqe\b", r"\bquality engineer", r"测试")),
    ("networking", _rx(
        r"\bnetwork(ing)?\b", r"\bccna\b", r"\brouting\b", r"\bswitching\b", r"\bwireless\b", r"\btelecom", r"\brf\b",
        r"\b5g\b", r"\blte\b", r"\bnoc\b", r"\bran\b", r"\boptical\b", r"\bvoip\b", r"\bsd-?wan\b")),
    ("it_support", _rx(
        r"\bit support\b", r"\bhelp ?desk\b", r"\bservice desk\b", r"\bdesktop support\b", r"\btechnical support\b",
        r"\bsupport engineer\b", r"\bsystem administrator\b", r"\bsysadmin\b", r"\bit (administrator|technician|specialist|analyst|operations)\b",
        r"\bapplication support\b", r"\bproduction support\b", r"\bl[123] support\b", r"\bit engineer\b", r"\bend user\b",
        r"\bdatabase administrator\b", r"\bdba\b", r"\bservicenow (admin|administrator)\b", r"\bmainframe operator\b",
        r"\b(system|systems|network|it|server|lead|cloud|windows|linux|backup|storage|middleware|technical) administrator\b")),
    ("consulting_tech", _rx(
        r"\bsap\b", r"\boracle (functional|consultant|fusion|ebs|hcm|erp)", r"\bsalesforce\b", r"\bservicenow\b",
        r"\bworkday (consultant|analyst|integration)", r"\berp\b", r"\bcrm\b", r"\bdynamics 365\b", r"\b(technology|it|digital|technical) consultant\b",
        r"\bsolutions? (architect|engineer|consultant)\b", r"\bbusiness analyst\b", r"\btechnical writer\b", r"\bscrum master\b",
        r"\bpre-?sales\b", r"\bimplementation (consultant|engineer|specialist)\b", r"\bpega\b", r"\bguidewire\b", r"\bpackage implementation\b",
        r"\btechnology (analyst|associate|specialist)\b", r"\bdigital transformation\b", r"\bintegration (developer|engineer|consultant)\b",
        r"\btechno[- ]?functional\b", r"\b(technical|enterprise|technology|solution|integration|application) architect\b",
        r"\btechnical (lead|manager|consultant|specialist|project manager|account manager)\b", r"\bfunctional consultant\b")),
    ("product_design", _rx(
        r"\bproduct (manager|owner|management)\b", r"\bux\b", r"\bui\b", r"\buser experience\b", r"\binteraction design",
        r"\bproduct design", r"\bvisual designer\b", r"\btechnical program manager\b", r"\btpm\b", r"\bux research", r"产品经理")),
    ("software", _rx(
        r"\bsoftware\b", r"\bdeveloper\b", r"\bdevelopment engineer\b", r"\bprogrammer\b", r"\bsde\b", r"\bswe\b",
        r"\bfull[- ]?stack\b", r"\bfront[- ]?end\b", r"\bback[- ]?end\b", r"\bweb\b", r"\bmobile\b", r"\bandroid\b", r"\bios\b",
        r"\bjava\b", r"\bpython\b", r"\.net\b", r"\bc\+\+", r"\bc#", r"\bgolang\b", r"\breact\b", r"\bangular\b", r"\bnode(\.js)?\b",
        r"\bmainframe\b", r"\bcobol\b", r"\bapplication (engineer|developer)\b", r"\bapi\b", r"\bmember of technical staff\b",
        r"\bengineer(ing)?\b", r"\bcoder\b", r"\bgame (developer|programmer|engineer)\b", r"\bunreal\b", r"开发|工程师|后台|前端")),
]
_NON_IT_WEAK = _rx(
    r"\bsales\b", r"\bfinance\b", r"\bfinancial\b", r"\btax\b", r"\blegal\b", r"\bhr\b", r"\bhuman resources\b",
    r"\boperations (associate|manager|specialist|coordinator)\b", r"\blogistics\b", r"\bsupply chain\b", r"\bcustomer service\b",
    r"\bcustomer success\b", r"\bcontent\b", r"\bcommunications?\b", r"\bfacilities\b", r"\bpeople (partner|operations)\b",
    r"\bbenefits\b", r"\bcompensation\b", r"\btreasury\b", r"\bcompliance\b", r"\brisk\b", r"\bclaims\b", r"\badvisory\b",
    r"\bassurance\b", r"\bactuar", r"\bclinical\b", r"\bmedical\b", r"\bretail\b", r"\bstore\b", r"\bmerchandis",
    r"\bproduction (worker|associate)\b", r"\bassembler\b", r"\boperator\b", r"\btechnician\b", r"运营|销售|市场|财务|法务|人力")


def _category_for(text: str) -> str | None:
    if not text:
        return None
    if _NON_IT_STRONG.search(text):
        return "non_it"
    for name, pattern in _CATEGORY_RULES:
        if pattern.search(text):
            return name
    if _NON_IT_WEAK.search(text):
        return "non_it"
    return None


def classify_category(title: str | None, department: str | None = None) -> str:
    return _category_for(title or "") or _category_for(department or "") or "other"
