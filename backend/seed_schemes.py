"""Idempotent seed script: upserts Telangana student scheme records.

Run:  python seed_schemes.py
Requires MONGODB_URI / MONGODB_DB env vars (or defaults from .env).
"""

import os
from datetime import date, datetime, time

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()

URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB = os.getenv("MONGODB_DB", "civicledger")

DOCS = ["Income certificate", "Caste certificate", "Bonafide certificate",
        "Fee receipt", "Aadhaar of parent/guardian (for portal verification only)",
        "Bank passbook (student account)", "Mark sheets / TC"]

def rule(t, label, value):
    return {"type": t, "label": label, "value": value}

SCHEMES = [
    {
        "slug": "epass-post-matric-sc",
        "name": "ePASS Post-Matric Scholarship — SC Students",
        "summary": "Tuition and maintenance support for SC students pursuing post-matric courses in Telangana colleges/universities.",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "category": "sc",
        "rules": [
            rule("residency", "Domicile", "Telangana resident for last 10 years"),
            rule("income_limit", "Family annual income", "Up to ₹2,00,000"),
            rule("attendance", "Attendance", "75%+ in previous year (indicative)"),
            rule("institution_type", "Institution", "Govt./aided college or university in Telangana"),
        ],
        "required_documents": DOCS,
        "application_steps": [
            "Register on the ePASS portal (epass.cgg.gov.in)",
            "Fill academic, income and bank details",
            "Upload scanned certificates",
            "Submit before the deadline and track status online",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 200000,
        "amount_or_benefit": "Tuition fee reimbursement + maintenance allowance",
    },
    {
        "slug": "epass-post-matric-ebc",
        "name": "ePASS Post-Matric Scholarship — BC/EBC Students",
        "summary": "Post-matric fee reimbursement and maintenance for BC and EBC category students in Telangana.",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "category": "ebc",
        "rules": [
            rule("residency", "Domicile", "Telangana resident for last 10 years"),
            rule("income_limit", "Family annual income", "Up to ₹2,00,000 (BC), ₹2,50,000 (EBC)"),
            rule("attendance", "Attendance", "75%+ in previous year (indicative)"),
            rule("institution_type", "Institution", "Govt./aided college or university in Telangana"),
        ],
        "required_documents": DOCS,
        "application_steps": [
            "Register on the ePASS portal (epass.cgg.gov.in)",
            "Fill academic, income and bank details",
            "Upload scanned certificates",
            "Submit before the deadline and track status online",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 250000,
        "amount_or_benefit": "Tuition fee reimbursement + maintenance allowance",
    },
    {
        "slug": "minority-post-matric",
        "name": "Minority Welfare Post-Matric Scholarship",
        "summary": "Financial assistance for students belonging to notified minority communities in Telangana pursuing post-matric studies.",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "category": "minority",
        "rules": [
            rule("residency", "Domicile", "Telangana resident minority student"),
            rule("income_limit", "Family annual income", "Up to ₹2,00,000"),
            rule("institution_type", "Institution", "Recognized college/university in or outside Telangana"),
        ],
        "required_documents": DOCS + ["Minority community certificate"],
        "application_steps": [
            "Apply via the Minority Welfare Department portal",
            "Enter academic and family income details",
            "Upload community and income certificates",
            "Track disbursement status online",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 200000,
        "amount_or_benefit": "Course fee reimbursement + maintenance",
    },
    {
        "slug": "nbs-fee-reimbursement",
        "name": "NBS Fee Reimbursement Scheme (BC/EBC)",
        "summary": "Reimbursement of tuition fees for eligible BC/EBC students in professional and post-matric courses.",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "education_levels": ["post_matric", "professional"],
        "category": "bc",
        "rules": [
            rule("residency", "Domicile", "Telangana BC/EBC resident"),
            rule("income_limit", "Family annual income", "Up to ₹1,50,000"),
            rule("merit", "Merit", "Minimum aggregate as prescribed (indicative)"),
        ],
        "required_documents": DOCS,
        "application_steps": [
            "Apply on the NBS portal during the notification window",
            "Verify fee receipt and category details",
            "Submit income and caste certificates",
            "Reimbursement credited after verification",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 150000,
        "amount_or_benefit": "Tuition fee reimbursement",
    },
    {
        "slug": "ambedkar-overseas-vidya-nidhi",
        "name": "Dr. B.R. Ambedkar Overseas Vidya Nidhi",
        "summary": "Merit-based overseas education funding for SC/ST students of Telangana for PG and research courses abroad.",
        "persona": "telangana_students",
        "education_level": "overseas",
        "category": "st",
        "rules": [
            rule("residency", "Domicile", "Telangana SC/ST resident"),
            rule("merit", "Merit", "First-class / merit as per selection committee"),
            rule("institution_type", "Institution", "Recognized foreign university for PG/research"),
        ],
        "required_documents": DOCS + [
            "Passport", "Admission offer letter from foreign university",
            "Statement of purpose", "Score reports (GRE/GMAT/IELTS as applicable)",
        ],
        "application_steps": [
            "Watch for the annual notification on the SC/ST welfare portal",
            "Apply online with offer letter and academic records",
            "Appear for interview/selection if shortlisted",
            "Grant disbursed as per approved amount",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in/OverseasLinks.do",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Up to ₹20 lakh for approved overseas PG/research courses (indicative)",
    },
    {
        "slug": "telangana-overseas-education",
        "name": "Telangana Overseas Education Scheme",
        "summary": "State support for meritorious Telangana students admitted to top-ranked foreign universities for UG/PG studies.",
        "persona": "telangana_students",
        "education_level": "overseas",
        "category": "all",
        "rules": [
            rule("residency", "Domicile", "Telangana resident"),
            rule("merit", "Merit", "Admission to top-ranked foreign institution; selection is competitive"),
            rule("institution_type", "Institution", "QS/top-ranked foreign university (indicative)"),
        ],
        "required_documents": DOCS + [
            "Passport", "Admission offer letter", "Score reports (IELTS/TOEFL/SAT as applicable)",
        ],
        "application_steps": [
            "Apply on the Overseas Education portal when notification opens",
            "Submit admission proof and academic records",
            "Selection committee reviews merit and need",
            "Selected students receive financial support",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Tuition + living expense support for selected students (indicative)",
    },
    {
        "slug": "epass-professional-fee-reimbursement",
        "name": "Professional Courses Fee Reimbursement",
        "summary": "Fee reimbursement support for students in professional degree courses (engineering, medicine, etc.) in Telangana.",
        "persona": "telangana_students",
        "education_level": "professional",
        "category": "all",
        "categories": ["sc", "st", "bc", "ebc", "minority"],
        "rules": [
            rule("residency", "Domicile", "Telangana resident"),
            rule("income_limit", "Family annual income", "Up to ₹2,00,000"),
            rule("institution_type", "Institution", "AICTE/UGC-recognized professional college in Telangana"),
            rule("attendance", "Attendance", "Minimum attendance as per college norms (indicative)"),
        ],
        "required_documents": DOCS,
        "application_steps": [
            "Check eligibility on the relevant welfare/epass portal",
            "Apply with fee receipts and income proof",
            "College nodal officer verifies and forwards",
            "Reimbursement processed after verification",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 200000,
        "amount_or_benefit": "Course fee reimbursement (capped as per norms)",
    },
    # ------------------------------------------------------------------
    # Persona: telangana_farmers
    # ------------------------------------------------------------------
    {
        "slug": "ts-rythu-bharosa",
        "name": "Rythu Bharosa — Investment Support",
        "summary": "Seasonal investment support for small and marginal farmers in Telangana with cultivable land.",
        "persona": "telangana_farmers",
        "rules": [
            rule("residency", "State", "Telangana resident"),
            rule("other", "Land record", "Cultivable land record required; converted land excluded"),
        ],
        "required_documents": [
            "Pattadar Passbook / Land Record Copy",
            "Active Bank Passbook Copy",
            "Registered Mobile Number",
        ],
        "application_steps": [
            "Verify land record details via MeeSeva/Revenue portal",
            "Submit agricultural account details to local AEO",
            "Track seasonal disbursement status",
        ],
        "rejection_pitfalls": [
            "Land records not matching Pattadar Passbook details",
            "Bank account not linked to the landholder's name",
        ],
        "official_url": "https://rythubharosa.telangana.gov.in/",
        "last_verified_date": "2026-11-21",
        "requires_cultivable_land": True,
        "amount_or_benefit": "Seasonal per-acre investment support (indicative)",
    },
    {
        "slug": "ts-rythu-bima",
        "name": "Rythu Bima — Farmer Life Insurance Scheme",
        "summary": "Life insurance cover for farmers aged 18-59 enrolled with the Agriculture Department.",
        "persona": "telangana_farmers",
        "rules": [
            rule("residency", "State", "Telangana resident"),
            rule("other", "Age", "18 to 59 years"),
            rule("other", "Enrollment", "Pattadar Passbook (PPB) / RoFR Patta holder"),
        ],
        "required_documents": [
            "Pattadar Passbook (PPB) / RoFR Patta",
            "Nominee Identity & Bank Details",
            "Land Title Copy",
        ],
        "application_steps": [
            "Enroll through local Agricultural Extension Officer (AEO)",
            "Designate beneficiary/nominee in land records",
            "Verify active enrollment on official portal",
        ],
        "rejection_pitfalls": [
            "Age outside the 18-59 window",
            "Nominee details missing from land records",
        ],
        "official_url": "https://web.umang.gov.in/landing/scheme/detail/rythu-bima-scheme_rythu-bima.html",
        "last_verified_date": "2026-11-21",
        "min_age": 18,
        "max_age": 59,
        "amount_or_benefit": "Life cover of ₹5 lakh (indicative)",
    },
    # ------------------------------------------------------------------
    # Persona: telangana_women_entrepreneurs
    # ------------------------------------------------------------------
    {
        "slug": "ts-indiramma-mahila-shakti",
        "name": "Indiramma Mahila Shakti — SHG Vaddi Leni Runalu",
        "summary": "Interest reimbursement and micro-credit support for women in SERP/MEPMA-registered SHGs.",
        "persona": "telangana_women_entrepreneurs",
        "gender": "female",
        "rules": [
            rule("residency", "State", "Telangana resident"),
            rule("other", "Gender", "Women members of registered SHGs"),
            rule("other", "SHG network", "Active membership in SERP or MEPMA SHG"),
        ],
        "required_documents": [
            "SHG Group Registration & Grading Certificate",
            "SHG Bank Account Passbook",
            "Micro-enterprise / Livelihood Project Plan",
        ],
        "application_steps": [
            "Apply through Village Organization (VO) / Mandal Samakhya",
            "Submit group credit & project proposal for SERP/MEPMA evaluation",
            "Receive bank linkage & interest reimbursement",
        ],
        "rejection_pitfalls": [
            "SHG registration or grading certificate expired",
            "Group bank account not active or KYC incomplete",
        ],
        "official_url": "https://www.efms.serp.telangana.gov.in/Livelihoods/TRIGP/MandalViews/HomeMHS.aspx",
        "last_verified_date": "2026-11-21",
        "requires_shg_membership": True,
        "amount_or_benefit": "Interest subvention on SHG micro-credit (indicative)",
    },
    {
        "slug": "ts-we-hub-incubation",
        "name": "WE Hub Foundation & Entrepreneurship Cohorts",
        "summary": "Incubation, mentorship and seed support for women founders via WE Hub cohorts.",
        "persona": "telangana_women_entrepreneurs",
        "gender": "female",
        "rules": [
            rule("residency", "State", "Telangana-based enterprise or founder"),
            rule("other", "Gender", "Women-owned enterprise (51%+ women ownership)"),
            rule("other", "Stage", "Aspiring founder, early-stage or scaling enterprise"),
        ],
        "required_documents": [
            "Pitch Deck / Business Summary",
            "Enterprise Registration (MSME/DPIIT if incorporated)",
            "Ownership Stake Proof",
        ],
        "application_steps": [
            "Select active cohort (WE Reach / Project Inclusion / WE Leads) on WE Hub portal",
            "Submit online application form with pitch details",
            "Participate in screening interview",
        ],
        "rejection_pitfalls": [
            "Women ownership below 51%",
            "Pitch deck missing traction or financial details",
        ],
        "official_url": "https://wehub.telangana.gov.in/sie/",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Incubation, mentorship and cohort grants (indicative)",
    },
    {
        "slug": "ts-kalyana-lakshmi",
        "name": "Kalyana Lakshmi / Shaadi Mubarak",
        "summary": "Marriage financial assistance for eligible brides from SC/ST/BC/EBC/Minority families in Telangana.",
        "persona": "telangana_women_entrepreneurs",
        "gender": "female",
        "category": "all",
        "categories": ["sc", "st", "bc", "ebc", "minority"],
        "rules": [
            rule("residency", "State", "Telangana resident"),
            rule("other", "Age", "Bride 18+, groom 21+"),
            rule("income_limit", "Family annual income", "Up to ₹2,00,000"),
            rule("other", "Category", "SC, ST, BC, EBC or Minority community"),
        ],
        "required_documents": [
            "Bride & Groom Age/Birth Proof",
            "Caste & Income Certificate",
            "Marriage Proof / Wedding Invitation",
            "Bride/Mother Bank Passbook Copy",
        ],
        "application_steps": [
            "Open Telangana ePASS portal and navigate to Kalyana Lakshmi / Shaadi Mubarak",
            "Fill bride, family, and wedding details without sensitive IDs",
            "Upload certificates and track verification status",
        ],
        "rejection_pitfalls": [
            "Bride under 18 or groom under 21",
            "Family income above ₹2,00,000",
            "Category certificate not among eligible communities",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in/",
        "last_verified_date": "2026-11-21",
        "min_age": 18,
        "max_annual_income_inr": 200000,
        "amount_or_benefit": "Marriage grant (indicative, as per category)",
    },
    {
        "slug": "ts-mjp-overseas-vidya-nidhi",
        "name": "Mahatma Jyothiba Phule Overseas Vidya Nidhi (BC/EBC)",
        "summary": "Merit-based overseas PG/PhD funding for economically backward BC/EBC students of Telangana.",
        "persona": "telangana_students",
        "education_level": "overseas",
        "category": "bc",
        "categories": ["bc", "ebc"],
        "rules": [
            rule("residency", "Domicile", "Telangana BC/EBC resident"),
            rule("income_limit", "Family annual income", "Below ₹5,00,000"),
            rule("merit", "Merit", "60% in graduation plus GRE/GMAT and English proficiency scores"),
            rule("institution_type", "Institution", "Top-ranked foreign university (USA, UK, Australia, Canada, Singapore, Germany, New Zealand, Japan, France, South Korea)"),
        ],
        "required_documents": DOCS + [
            "Passport", "Admission offer letter / COE / I-20",
            "GRE/GMAT and IELTS/TOEFL/PTE score reports",
        ],
        "application_steps": [
            "Register on the ePASS Overseas links page when the window opens",
            "Submit graduation marks and test scores for merit listing",
            "Shortlisted candidates verify documents in person",
            "Grant released in installments as per approval",
        ],
        "rejection_pitfalls": [
            "Family income at or above ₹5 lakh",
            "Missing GRE/GMAT or English proficiency scores",
            "Applying without COE/I-20 and visa as required",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in/OverseasLinks.do",
        "last_verified_date": "2026-11-21",
        "max_annual_income_inr": 500000,
        "amount_or_benefit": "Up to ₹20 lakh plus one-way ticket and visa charges (indicative)",
    },
    {
        "slug": "ts-minority-overseas-study",
        "name": "Chief Minister's Overseas Study Scheme — Minorities",
        "summary": "Overseas PG/PhD scholarship for meritorious students from Telangana's minority communities.",
        "persona": "telangana_students",
        "education_level": "overseas",
        "category": "minority",
        "rules": [
            rule("residency", "Domicile", "Telangana minority community resident"),
            rule("income_limit", "Family annual income", "Below ₹3,00,000 (indicative)"),
            rule("merit", "Merit", "60% in graduation plus eligible GRE/GMAT and English test scores"),
            rule("institution_type", "Institution", "Approved foreign university for PG/PhD"),
        ],
        "required_documents": DOCS + [
            "Passport", "Admission offer letter / COE / I-20",
            "Minority community certificate", "GRE/GMAT and IELTS/TOEFL/PTE score reports",
        ],
        "application_steps": [
            "Register via the ePASS Overseas links page for minority students",
            "Submit academic records, test scores and offer letter",
            "Document verification by the selection committee",
            "Financial assistance released in installments",
        ],
        "rejection_pitfalls": [
            "Missing minority community certificate",
            "Income above the prescribed ceiling",
            "Changing university or course after sanction",
        ],
        "official_url": "https://telanganaepass.cgg.gov.in/OverseasLinks.do",
        "last_verified_date": "2026-11-21",
        "max_annual_income_inr": 300000,
        "amount_or_benefit": "Tuition and living support up to sanctioned limit (indicative)",
    },
    # ------------------------------------------------------------------
    # Persona: telangana_farmers
    # ------------------------------------------------------------------
    {
        "slug": "ts-rythu-runa-mafi",
        "name": "Telangana Crop Loan Waiver (Rythu Runa Mafi)",
        "summary": "Government waiver of crop loans up to ₹2 lakh per farmer family, including interest, disbursed under notified windows.",
        "persona": "telangana_farmers",
        "rules": [
            rule("residency", "State", "Telangana resident farmer"),
            rule("other", "Loan", "Crop loan availed from a scheduled bank, cooperative or RRB within the notified period"),
            rule("other", "Identity", "Food security card / ration card used for family identification"),
        ],
        "required_documents": [
            "Pattadar Passbook / Land Record Copy",
            "Loan account details (crop loan only)",
            "Ration card for family identification",
            "Registered bank account",
        ],
        "application_steps": [
            "Check the Crop Loan Waiver portal during an active notification",
            "Ensure loan and land records match beneficiary details",
            "Waiver amount credited directly to the loan account",
            "Raise grievances via the portal committee if not credited",
        ],
        "rejection_pitfalls": [
            "Loan taken outside the notified waiver window",
            "Personal or non-crop loans are not covered",
            "Land records not matching the loan account holder",
        ],
        "official_url": "https://clw.telangana.gov.in/About.aspx",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Loan waiver up to ₹2,00,000 per farmer family (indicative, window-dependent)",
    },
    # ------------------------------------------------------------------
    # Persona: telangana_women_entrepreneurs
    # ------------------------------------------------------------------
    {
        "slug": "ts-serp-day-nrlm-incubator",
        "name": "SERP DAY-NRLM Women Enterprise Incubator",
        "summary": "18-month incubation, mentoring and market-linkage support for SHG-linked women-led rural enterprises in Telangana.",
        "persona": "telangana_women_entrepreneurs",
        "gender": "female",
        "requires_shg_membership": True,
        "rules": [
            rule("residency", "State", "Telangana resident"),
            rule("other", "Gender", "Women-owned or women-led enterprise"),
            rule("other", "SHG link", "Enterprise linked to an SHG member"),
            rule("other", "Turnover", "Annual turnover above ₹12 lakh in manufacturing or services (indicative)"),
        ],
        "required_documents": [
            "SHG membership / group registration proof",
            "Enterprise details and business plan",
            "Bank account and turnover records (indicative)",
        ],
        "application_steps": [
            "Apply via the SERP SHG app or the Accubate platform",
            "Shortlisting and enterprise diagnostics follow",
            "Selected enterprises get 18 months of incubation support",
            "Monitor progress through the SERP tracking system",
        ],
        "rejection_pitfalls": [
            "Enterprise not linked to an SHG member",
            "Women ownership below majority stake",
            "Annual turnover below the prescribed threshold",
        ],
        "official_url": "https://www.serp.telangana.gov.in/incubator/incub.jsp",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Incubation, mentoring, challenge fund and market linkage (indicative)",
    },
    # ------------------------------------------------------------------
    # Central schemes (Government of India) — open to Telangana residents
    # ------------------------------------------------------------------
    {
        "slug": "central-nsp-post-matric",
        "name": "NSP — Post-Matric Scholarship (Central Sector)",
        "summary": "Central government post-matric scholarships disbursed via the National Scholarship Portal for eligible students.",
        "scheme_level": "central",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "education_levels": ["post_matric", "professional"],
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian citizen; Telangana residents apply via the state nodal agency"),
            rule("income_limit", "Family annual income", "Varies by scholarship component (indicative)"),
            rule("institution_type", "Institution", "Recognized college/university in India"),
        ],
        "required_documents": DOCS,
        "application_steps": [
            "Register on the National Scholarship Portal (scholarships.gov.in)",
            "Fill academic, income and bank details; submit to the state nodal officer",
            "Track disbursement status on the NSP dashboard",
        ],
        "official_url": "https://scholarships.gov.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Tuition fee + maintenance support (component-wise, indicative)",
    },
    {
        "slug": "central-insPIRE",
        "name": "INSPIRE Scholarship — Science Students",
        "summary": "Department of Science & Technology merit-cum-means scholarship for students pursuing basic sciences at UG/PG level.",
        "scheme_level": "central",
        "persona": "telangana_students",
        "education_level": "post_matric",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian citizen"),
            rule("merit", "Merit", "Top 1% in Class XII board exam or valid JEE/NEET/other national rank (indicative)"),
            rule("institution_type", "Institution", "Recognized Indian university/college offering basic sciences"),
        ],
        "required_documents": DOCS + ["Class XII marksheet", "Rank/JEE/NEET scorecard (if applicable)"],
        "application_steps": [
            "Apply online at online-inspire.gov.in within the notified window",
            "Upload marksheets and rank proof",
            "Renewal requires continuation in the same course",
        ],
        "official_url": "https://online-inspire.gov.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "₹80,000 per year for 5 years (indicative)",
    },
    {
        "slug": "central-aicte-pragati",
        "name": "AICTE Pragati — Girls in Technical Education",
        "summary": "Scholarship for girl students in AICTE-approved technical diploma and degree programmes from families with modest income.",
        "scheme_level": "central",
        "persona": "telangana_students",
        "education_level": "professional",
        "category": "all",
        "gender": "female",
        "rules": [
            rule("residency", "Residence", "Indian citizen"),
            rule("income_limit", "Family annual income", "Up to ₹8,00,000"),
            rule("other", "Gender", "Girl student enrolled in AICTE-approved technical programme"),
        ],
        "required_documents": DOCS + ["AICTE-approved institution bonafide"],
        "application_steps": [
            "Apply via the AICTE student portal during the notified window",
            "Upload income and category certificates",
            "Disbursement is routed through the institution/DBT",
        ],
        "official_url": "https://rules.myscheme.gov.in/en/check-eligibility/psgs-deg",
        "last_verified_date": "2026-11-21",
        "max_income_limit": 800000,
        "amount_or_benefit": "Tuition fee reimbursement + incidentals (indicative)",
    },
    {
        "slug": "central-pm-kisan",
        "name": "PM-KISAN — Income Support for Farmers",
        "summary": "Direct income support of ₹6,000 per year (three instalments) for landholding farmer families across India.",
        "scheme_level": "central",
        "persona": "telangana_farmers",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian citizen and resident"),
            rule("other", "Landholding", "Small/marginal landholding farmer family"),
            rule("other", "Exclusions", "Institutional landholders and income-tax payers in some categories excluded (indicative)"),
        ],
        "required_documents": [
            "Land records / Pattadar Passbook",
            "Aadhaar (for eKYC on portal only)",
            "Bank account passbook",
            "Caste certificate (if applicable)",
        ],
        "application_steps": [
            "Register at pmkisan.gov.in with Aadhaar eKYC",
            "Landholding details are verified against state records",
            "Instalments credited directly to the bank account",
        ],
        "official_url": "https://pmkisan.gov.in",
        "last_verified_date": "2026-11-21",
        "requires_cultivable_land": True,
        "amount_or_benefit": "₹6,000 per year in three instalments",
    },
    {
        "slug": "central-kcc",
        "name": "Kisan Credit Card (KCC) Scheme",
        "summary": "Short-term crop loans and investment credit at subsidized rates through banks under the RBI/NABARD KCC framework.",
        "scheme_level": "central",
        "persona": "telangana_farmers",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian farmer / tenant farmer / SHG"),
            rule("other", "Purpose", "Crop production, post-harvest, allied activities or farm investment"),
        ],
        "required_documents": [
            "Land records / tenancy proof",
            "Identity and address proof",
            "Passport-size photograph",
            "Crop plan / purpose declaration",
        ],
        "application_steps": [
            "Apply at your bank branch or via the bank's KCC portal",
            "Submit land and identity documents",
            "Sanctioned limit is usually renewed annually",
        ],
        "official_url": "https://www.nabard.org",
        "last_verified_date": "2026-11-21",
        "requires_cultivable_land": True,
        "amount_or_benefit": "Crop loan up to the scale of finance, interest subvention (indicative)",
    },
    {
        "slug": "central-pmfby",
        "name": "PM Fasal Bima Yojana (PMFBY)",
        "summary": "Crop insurance with capped premiums protecting farmers against yield losses from natural calamities.",
        "scheme_level": "central",
        "persona": "telangana_farmers",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian farmer cultivating notified crops"),
            rule("other", "Crop", "Notified crops in notified areas only"),
            rule("income_limit", "Premium share", "Farmers pay only 1-2% of sum insured for food crops (indicative)"),
        ],
        "required_documents": [
            "Land records / sowing certificate",
            "Identity proof",
            "Bank account details",
            "Caste certificate (if applicable)",
        ],
        "application_steps": [
            "Enroll via the PMFBY portal, bank, or CSC before the cutoff",
            "Premium is auto-debited or paid at enrolment",
            "Claims are settled after crop-cutting assessment on yield loss",
        ],
        "official_url": "https://pmfby.gov.in",
        "last_verified_date": "2026-11-21",
        "requires_cultivable_land": True,
        "amount_or_benefit": "Yield-loss insurance at capped premium (indicative)",
    },
    {
        "slug": "central-pmegp",
        "name": "PMEGP — Prime Minister's Employment Generation Programme",
        "summary": "Credit-linked subsidy for new micro-enterprises, implemented through KVIC and state KVIBs.",
        "scheme_level": "central",
        "persona": "telangana_women_entrepreneurs",
        "category": "all",
        "min_age": 18,
        "max_age": 59,
        "rules": [
            rule("residency", "Residence", "Indian resident"),
            rule("other", "Age", "18 to 59 years"),
            rule("other", "Enterprise", "New micro enterprise; no existing PMEGP subsidy (indicative)"),
            rule("other", "Subsidy", "25-35% of project cost depending on area/category (indicative)"),
        ],
        "required_documents": [
            "Identity and address proof",
            "Caste/EWS certificate (if applicable)",
            "Project report",
            "Bank account details",
        ],
        "application_steps": [
            "Apply online at the PMEGP portal (pmegp.msme.gov.in)",
            "Interview by the KVIB/KVIC task force",
            "Bank sanctions the term loan; subsidy is released in tranches",
        ],
        "official_url": "https://pmegp.msme.gov.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "25-35% subsidy on project cost up to prescribed limits (indicative)",
    },
    {
        "slug": "central-mudra",
        "name": "MUDRA Yojana — Collateral-Free Business Loans",
        "summary": "Bank loans for micro and small enterprises in manufacturing, services and allied activities, including SHG women borrowers.",
        "scheme_level": "central",
        "persona": "telangana_women_entrepreneurs",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian resident entrepreneur"),
            rule("other", "Enterprise", "Micro/small enterprise in non-farm sector"),
            rule("other", "Loan slabs", "Shishu up to ₹50k, Kishor up to ₹5L, Tarun up to ₹10L (indicative)"),
        ],
        "required_documents": [
            "Identity and address proof",
            "Business proof / project details",
            "Bank account passbook",
            "Caste certificate (if applicable)",
        ],
        "application_steps": [
            "Apply through any scheduled bank offering MUDRA loans",
            "Banks classify the loan into Shishu/Kishor/Tarun slab",
            "Repayment as per bank terms; no collateral for most loans",
        ],
        "official_url": "https://www.mudra.org.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Collateral-free loans up to ₹10 lakh (indicative)",
    },
    {
        "slug": "central-standup-india",
        "name": "Stand-Up India — Loans for Women/SC/ST Entrepreneurs",
        "summary": "Bank loans of ₹10 lakh to ₹1 crore for greenfield enterprises by women and SC/ST entrepreneurs.",
        "scheme_level": "central",
        "persona": "telangana_women_entrepreneurs",
        "category": "all",
        "rules": [
            rule("residency", "Residence", "Indian resident"),
            rule("other", "Beneficiary", "Women entrepreneur or SC/ST entrepreneur"),
            rule("other", "Enterprise", "Greenfield (new) enterprise in manufacturing/services/agri-allied"),
        ],
        "required_documents": [
            "Identity and address proof",
            "Caste certificate (SC/ST applicants)",
            "Business/project plan",
            "Bank account details",
        ],
        "application_steps": [
            "Register at standupmitra.in and get handholding support",
            "Approach a Stand-Up India-enabled bank branch",
            "Bank appraises and sanctions the composite loan",
        ],
        "official_url": "https://www.standupmitra.in",
        "last_verified_date": "2026-11-21",
        "amount_or_benefit": "Composite loan ₹10 lakh to ₹1 crore (indicative)",
    },
]


def main() -> None:
    client = MongoClient(URI)
    coll = client[DB]["schemes"]
    coll.create_index("slug", unique=True)

    ops = []
    for s in SCHEMES:
        doc = dict(s)
        doc["active"] = True
        persona = s.get("persona", "telangana_students")
        doc["persona"] = persona
        doc["target_group"] = persona
        doc["scheme_level"] = s.get("scheme_level", "state")
        # BSON cannot encode datetime.date; store midnight UTC instead.
        doc["last_verified_date"] = datetime.combine(
            date.fromisoformat(s["last_verified_date"]), time.min
        )
        ops.append(UpdateOne({"slug": s["slug"]}, {"$set": doc}, upsert=True))

    result = coll.bulk_write(ops)
    print(f"Seeded {result.upserted_count} new, {result.modified_count} updated "
          f"(total ops: {len(ops)})")
    client.close()


if __name__ == "__main__":
    main()
