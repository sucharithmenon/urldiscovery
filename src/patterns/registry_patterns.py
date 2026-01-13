"""Supplemental ATS detection regex from ats_complete_ultra_deep_dive.xlsx."""

REGISTRY_PATTERNS = {
    "ADP_WORKFORCE_NOW": [
        r"workforcenow\.adp\.com",
    ],
    "APPLICANTPRO": [
        r"\.applicantpro\.com/jobs",
    ],
    "APPLICANTSTACK": [
        r"\.applicantstack\.com",
    ],
    "ASHBY": [
        r"jobs\.ashbyhq\.com",
    ],
    "AVATURE": [
        r"\.avature\.net",
    ],
    "BAMBOOHR": [
        r"\.bamboohr\.com/careers",
    ],
    "BEAMERY": [
        r"beamery\.com",
    ],
    "BETTERTEAM": [
        r"betterteam\.com",
    ],
    "BREEZY_HR": [
        r"\.breezy\.hr",
    ],
    "BULLHORN": [
        r"bullhornstaffing\.com",
    ],
    "CADIENT": [
        r"cadienttalent\.com",
    ],
    "CATS": [
        r"\.catsone\.com/careers",
    ],
    "CEIPAL": [
        r"ceipal\.com/job",
    ],
    "CLEARCOMPANY": [
        r"\.hrmdirect\.com",
    ],
    "COMEET_SPARK_HIRE": [
        r"comeet\.co/jobs",
    ],
    "DARWINBOX": [
        r"\.darwinbox\.io/ms/candidate/careers",
    ],
    "DAYFORCE_CERIDIAN": [
        r"\.dayforcehcm\.com/CandidatePortal",
    ],
    "DOVER": [
        r"app\.dover\.io/apply",
    ],
    "EIGHTFOLD_AI": [
        r"eightfold\.ai",
    ],
    "FACTOHR": [
        r"factohr\.com",
    ],
    "FOUNTAIN": [
        r"jobs\.fountain\.com",
    ],
    "FRESHTEAM": [
        r"\.freshteam\.com/jobs",
    ],
    "GEM": [
        r"jobs\.gem\.com",
    ],
    "GREENHOUSE": [
        r"boards\.greenhouse\.io",
    ],
    "GREYTHR": [
        r"\.greythr\.com.*careers",
    ],
    "HARRI": [
        r"\.harri\.com/apply",
    ],
    "HEALTHCARESOURCE": [
        r"healthcaresource\.com",
    ],
    "HIBOB": [
        r"\.careers\.hibob\.com",
    ],
    "HIREEZ": [
        r"hireez\.com|hiretual\.com",
    ],
    "HIREOLOGY": [
        r"careers\.hireology\.com",
    ],
    "HRONE": [
        r"hrone\.cloud",
    ],
    "ICIMS": [
        r"icims\.com|\.icims\.",
    ],
    "IDEALTRAITS": [
        r"idealtraits\.com",
    ],
    "JAZZHR": [
        r"\.applytojob\.com",
    ],
    "JOBDIVA": [
        r"jobdiva\.com/portal",
    ],
    "JOBVITE": [
        r"jobs\.jobvite\.com",
    ],
    "JOIN_DOT_COM": [
        r"join\.com/companies",
    ],
    "KEKA": [
        r"\.keka\.com/careers",
    ],
    "LEVER": [
        r"jobs\.lever\.co",
    ],
    "LOXO": [
        r"app\.loxo\.co/job",
    ],
    "MANATAL": [
        r"apply\.manatal\.com",
    ],
    "MOKA": [
        r"mokahr\.com",
    ],
    "NEOGOV": [
        r"governmentjobs\.com/careers",
    ],
    "OORWIN": [
        r"\.oorwin\.com/careers",
    ],
    "ORACLE_TALEO": [
        r"\.taleo\.net/careersection",
    ],
    "PAYCOM": [
        r"paycomonline\.net/v4/ats",
    ],
    "PAYCOR": [
        r"recruiting\.paycor\.com",
    ],
    "PAYLOCITY": [
        r"recruiting\.paylocity\.com",
    ],
    "PEOPLESTRONG": [
        r"\.peoplestrong\.com",
    ],
    "PERSONIO": [
        r"\.jobs\.personio\.com",
    ],
    "PHENOM_PEOPLE": [
        r"phenom\.com|phenompeople",
    ],
    "PINPOINT": [
        r"\.pinpointhq\.com",
    ],
    "PYJAMAHR": [
        r"pyjamahr\.com",
    ],
    "RECOOTY": [
        r"jobs\.recooty\.com",
    ],
    "RECRUITEE": [
        r"\.recruitee\.com",
    ],
    "RECRUIT_CRM": [
        r"portal\.recruitcrm\.io",
    ],
    "RIPPLING": [
        r"ats\.rippling\.com/careers",
    ],
    "SAGE_HR": [
        r"sage\.hr",
    ],
    "SAP_SUCCESSFACTORS": [
        r"successfactors\.com|jobs\.sap\.com",
    ],
    "SKILLATE": [
        r"\.skillate\.com",
    ],
    "SMARTRECRUITERS": [
        r"jobs\.smartrecruiters\.com",
    ],
    "SOFTGARDEN": [
        r"softgarden\.de",
    ],
    "SPRINGRECRUIT": [
        r"springrecruit\.com|springworks",
    ],
    "SYMPLR_API_HEALTHCARE": [
        r"symplr|api\.healthcare",
    ],
    "TALENTREEF": [
        r"talentreef",
    ],
    "TALOS360": [
        r"\.talosats-careers\.com",
    ],
    "TEAMTAILOR": [
        r"career\.teamtailor\.com|teamtailor-app",
    ],
    "TURBOHIRE": [
        r"\.turbohire\.co/careerpage",
    ],
    "UKG_PRO": [
        r"recruiting\.ultipro\.com",
    ],
    "USAJOBS": [
        r"usajobs\.gov",
    ],
    "WELLFOUND_ANGELLIST": [
        r"wellfound\.com/company/.*/jobs",
    ],
    "WORKABLE": [
        r"apply\.workable\.com",
    ],
    "WORKDAY": [
        r"myworkdayjobs\.com/[^/]+",
    ],
    "ZAPPYHIRE": [
        r"zappyhire\.com",
    ],
    "ZING_HR": [
        r"zinghr\.com",
    ],
    "ZOHO_RECRUIT": [
        r"zohorecruit\.com|zoho\.com/recruit",
    ],
}