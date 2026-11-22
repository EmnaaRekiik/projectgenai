"""FICTITIOUS demonstration catalogue. None of this is official IIT/ISB information.

Every title is prefixed "[DÉMO]" and every programme code starts with "DEMO-". Amounts, rules and
courses are invented only so that the API, the chat and the frontend can be exercised. Real data
must come from verified official sources (see docs/API_CONTRACT.md).
"""

DEMO_PREFIX = "DEMO-"
DEMO_SOURCE_URL = (
    "https://demo.invalid/donnees-fictives"  # .invalid is reserved: it can never resolve
)
DEMO_NOTE = "Donnée fictive de démonstration. Ne pas utiliser comme information officielle."

# (email, display name, role, institution code or None). example.org is reserved for documentation.
DEMO_STAFF = (
    ("demo.admin@example.org", "Démo Administrateur", "PLATFORM_ADMIN", None),
    ("demo.iit@example.org", "Démo Responsable IIT", "ACADEMIC_IIT", "IIT"),
    ("demo.isb@example.org", "Démo Responsable ISB", "ACADEMIC_ISB", "ISB"),
    ("demo.entretien@example.org", "Démo Responsable entretien", "INTERVIEW_MANAGER", None),
    ("demo.direction@example.org", "Démo Direction", "DIRECTION", None),
)

_RULES = (
    (
        "ADMISSION",
        "[DÉMO] Dossier de candidature",
        "Dossier à déposer avant la date limite fixée par l'établissement (exemple fictif).",
    ),
    (
        "PREREQUISITE",
        "[DÉMO] Baccalauréat",
        "Baccalauréat ou équivalent, série à préciser par l'établissement (exemple fictif).",
    ),
    (
        "DOCUMENT",
        "[DÉMO] Relevés de notes",
        "Copie des relevés de notes des deux dernières années (exemple fictif).",
    ),
)

# courses: (code, title, semester, credits, specialization code or None)
DEMO_PROGRAMS = (
    {
        "institution": "IIT",
        "code": "DEMO-IIT-LIC-INFO",
        "level": "LICENCE",
        "duration_years": 3,
        "title": "[DÉMO] Licence en informatique (exemple)",
        "specializations": (
            ("DEMO-GL", "[DÉMO] Génie logiciel", "Parcours fictif orienté développement logiciel."),
            (
                "DEMO-SI",
                "[DÉMO] Systèmes d'information",
                "Parcours fictif orienté conception de systèmes d'information.",
            ),
        ),
        "courses": (
            ("ALGO1", "Algorithmique et programmation 1", 1, 6, None),
            ("MATH1", "Analyse mathématique 1", 1, 5, None),
            ("ARCH1", "Architecture des ordinateurs", 2, 4, None),
            ("BDD1", "Bases de données", 3, 5, None),
            ("WEB1", "Développement web", 5, 5, "DEMO-GL"),
            ("SI1", "Modélisation des systèmes d'information", 5, 5, "DEMO-SI"),
        ),
        "tuition": 4800,
    },
    {
        "institution": "IIT",
        "code": "DEMO-IIT-PREPA",
        "level": "PREPARATORY",
        "duration_years": 2,
        "title": "[DÉMO] Cycle préparatoire intégré (exemple)",
        "specializations": (),
        "courses": (
            ("MATH-P1", "Mathématiques générales", 1, 8, None),
            ("PHYS-P1", "Physique", 1, 6, None),
            ("INFO-P1", "Initiation à l'informatique", 2, 5, None),
            ("ALGO-P2", "Algorithmique", 2, 5, None),
        ),
        "tuition": 4200,
    },
    {
        "institution": "IIT",
        "code": "DEMO-IIT-ING-INFO",
        "level": "ENGINEERING",
        "duration_years": 3,
        "title": "[DÉMO] Cycle ingénieur en informatique (exemple)",
        "specializations": (
            (
                "DEMO-IA",
                "[DÉMO] Intelligence artificielle",
                "Parcours fictif orienté apprentissage automatique.",
            ),
            (
                "DEMO-CYBER",
                "[DÉMO] Cybersécurité",
                "Parcours fictif orienté sécurité des systèmes.",
            ),
        ),
        "courses": (
            ("ARCHI-L", "Architecture logicielle", 1, 5, None),
            ("RES1", "Réseaux avancés", 2, 5, None),
            ("ML1", "Apprentissage automatique", 4, 6, "DEMO-IA"),
            ("SEC1", "Sécurité des systèmes", 4, 6, "DEMO-CYBER"),
            ("PFE", "Projet de fin d'études", 6, 30, None),
        ),
        "tuition": 6000,
    },
    {
        "institution": "ISB",
        "code": "DEMO-ISB-LIC",
        "level": "LICENCE",
        "duration_years": 3,
        "title": "[DÉMO] Licence ISB (exemple)",
        "specializations": (),
        "courses": (
            ("GEST1", "Principes de gestion", 1, 5, None),
            ("COMM1", "Communication professionnelle", 1, 4, None),
            ("STAT1", "Statistiques appliquées", 2, 5, None),
        ),
        "tuition": 3900,
    },
    {
        "institution": "ISB",
        "code": "DEMO-ISB-SPEC",
        "level": "OTHER",
        "duration_years": 1,
        "title": "[DÉMO] Formation spécialisée ISB (exemple)",
        "specializations": (),
        "courses": (
            ("PROJ1", "Gestion de projet", 1, 6, None),
            ("ENTR1", "Entrepreneuriat", 2, 6, None),
        ),
        "tuition": 2500,
    },
)


def rules():
    return _RULES
