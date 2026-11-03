"""Tech-adjacent title check (D27). Measured on 2026-10-15 against 1,763 titles jseek.co labels by
occupation: 99.1% of tech titles kept, 94.1% of non-tech titles dropped."""

import pytest

from src.core.tech_gate import drop_at_monitor, is_tech_title


@pytest.mark.parametrize("title", [
    "Software Engineer II - Java", "SDE-1", "MTS 2", "Member of Technical Staff", "Staff Software Engineer",
    "Principal Systems Software Engineer", "Java Backend Engineer", "Software Engineer Apprenticeship",
    "Graduate Engineer Trainee", "Data Analyst Intern", "Machine Learning Engineer", "Data Scientist",
    "Site Reliability Engineer", "Embedded Software Engineer", "VLSI Design Engineer", "UI/UX Designer",
    "Associate Product Manager", "Technical Program Manager", "Program Manager", "Engineering Manager",
    "Solutions Architect", "Sales Engineer", "Business Analyst", "Security Engineer", "QA Automation Engineer",
    "Consultant SAP PY", "Incident Response Sr. Consultant (Remote)",  # tech words outrank "consultant"
    "下一代推荐大模型算法工程师 - TikTok算法", "供应链项目经理-芯片", "デリバリーソリューションアーキテクト",
    "Специалист контрольных систем управления",  # non-CJK, non-Latin titles can't be judged, so they're kept
    # A tech role outranks a non-tech role word (D42).
    "Sales Engineer - Cloud", "Marketing Data Analyst", "Salesforce Developer", "Pre-Sales Solution Architect",
    "Information Systems Security Officer (ISSO)", "2027 Technical Sales Intern - Equipment",
    "SAP SD Consultant (Sales and Distribution)", "Software Engineer, Retail", "Migration Delivery Lead - Marketing Cloud",
    "Front End Engineer", "Apps Development Group Manager",
])
def test_tech_titles_are_kept(title):
    assert is_tech_title(title)


@pytest.mark.parametrize("title", [
    "Restaurant General Manager", "Crew Member", "Shift Manager", "Store Associate", "Cashier", "Barista",
    "Registered Nurse", "Pharmacist", "Warehouse Associate", "Delivery Driver", "Teacher", "Electrician",
    "Sales Associate", "Accountant", "HR Business Partner", "Customer Service Representative",
    "Marketing Manager", "Trainee", "Data Entry Operator", "Customer Success Manager",
    "Senior Relationship Executive - MFI South", "Praktikum Werkleitung und Fahrzeugbau Wolfsburg (w/m/d)",
    # Non-tech role words outrank tech words and the taxonomy's engineering-manager match (D42).
    "Business Development Manager", "Sales Development Manager", "Cloud Account Executive",
    "Cortex Cloud Sales Specialist", "Digital Marketing Specialist", "Director, Product Marketing",
    "FRONT END/CASHIER", "Front End Entry Level", "FRONT END/ASST DEPT LEADER", "Retail Display Installer – Technology", "Product Demonstrator PT",
    "Security Officer - Nights", "Armed Security Officer", "Data Center Security Officer", "CT Tech - Per Diem",
    "Mammography Tech PRN", "Relationship Officer - 811 Digital Sales - Digital Banking",
    # Chinese, Japanese and Korean titles without a tech word.
    "兼职 | 星级咖啡师（学生兼职）", "医药代表（广州-基石产品线）", "ドミノ・ピザの宅配ドライバー", "배민B마트 광주광산점 일일크루(단기) 모집",
])
def test_non_tech_titles_are_dropped(title):
    assert not is_tech_title(title)


@pytest.mark.parametrize("title", [None, "", "   "])
def test_untitled_jobs_are_kept(title):
    assert is_tech_title(title)


@pytest.mark.parametrize("url,title,dropped", [
    ("https://x.io/1", "Cashier", True),
    ("https://x.io/1", "Data Engineer", False),
    ("https://mcd.com/job/Chicago-Restaurant-Crew-Member/1", None, True),
    ("https://x.com/job/Registered-Nurse-ICU/9", None, True),
    ("https://x.com/job/Store-Manager-Mumbai/9", None, True),
    # Vague or id-only slugs are kept and judged after the scrape.
    ("https://x.com/en-us/open-positions/123", None, False),
    ("https://boards.greenhouse.io/acme/jobs/123", None, False),
    ("https://x.com/job/Bengaluru/Software-Engineer_R1", None, False),
    ("https://x.com/job/Data-Center-Technician/9", None, False),
    ("https://x.com/job/IT-Support-Technician/9", None, False),
])
def test_drop_at_monitor(url, title, dropped):
    assert drop_at_monitor(url, title) is dropped


WD = "https://acme.wd5.myworkdayjobs.com/External/job"


@pytest.mark.parametrize("url,dropped", [
    # Workday and iCIMS put the real title in the URL, so it is judged like a title (D35).
    (f"{WD}/Plano-TX/Store-Associate_R12345-1", True),
    (f"{WD}/Ipswich/Senior-Wealth-Planner---Mass-Affluent_JR-0000100217-1", True),
    (f"{WD}/Bengaluru/Senior-Software-Engineer_R123", False),
    (f"{WD}/San-Jose-California-US/ASIC-Engineering-Technical-Leader_2006625", False),
    ("https://careers-x.icims.com/jobs/1706473/part-time-grocery-stock-clerk/job", True),
    ("https://careers-x.icims.com/jobs/19057/experienced-component-engineer/job", False),
    # Too little to judge: kept for the scrape.
    (f"{WD}/Pune/Manager_R1", False),
    (f"{WD}/Tokyo/XMLNAME--2027-_R9", False),
])
def test_drop_at_monitor_ats_slug_titles(url, dropped):
    assert drop_at_monitor(url, None) is dropped


@pytest.mark.parametrize("title,tech", [
    ("Mobile Associate - Retail Sales", False),
    ("Senior Mobile Engineer", True),
    ("Team Lead Mobile Development", True),
    ("Mobile App Developer", True),
])
def test_mobile_counts_only_as_mobile_software(title, tech):
    assert is_tech_title(title) is tech
