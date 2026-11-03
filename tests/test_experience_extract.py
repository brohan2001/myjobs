"""Years-of-experience extraction: real phrasings from Indian boards (2026-11-02 sample) and known false positives."""

import pytest

from src.core.experience_extract import estimate_experience, extract_experience


@pytest.mark.parametrize(
    ("html", "want"),
    [
        ("<p>5+ years of experience in Java</p>", (5, None)),
        ("<li>3-5 years of software development experience</li>", (3, 5)),
        ("Minimum 3 year(s) of experience is required", (3, None)),  # Accenture
        ("<b>Experience:</b> 3-5 Years", (3, 5)),  # Wipro
        ("Your Profile Total Experience: 6-9 Years Only", (6, 9)),  # Capgemini
        ("Qualifications: Any Graduation Years of Experience: 3 to 5 years About Accenture", (3, 5)),
        ("Years of Exp: 10 to 15 years", (10, 15)),
        ("Experience: &gt;10 YEARS", (10, None)),
        ("Experience : 2–6 Years", (2, 6)),
        ("3 to 5 years of relevant experience", (3, 5)),
        ("1-3 years’ experience in GMP regulated environment", (1, 3)),
        # 2026-11-03 sample of India jobs the patterns missed
        ("Requirements 8+ years as a software engineer, including time leading", (8, None)),
        ("5+ years in test automation or software engineering in test", (5, None)),
        ("Experience 10-20 years Industry Preferred", (10, 20)),
        ("Skills- AWS, Python/Nodejs Exp- 6+ years Location- Pune", (6, None)),
        ("Experience (7+ years) in implementing security engineering projects", (7, None)),
        ("Job Description Experience between 4-7yrs. - Implement new enhancements", (4, 7)),
        ("Support Level: L2/L3 Experience: Typically 4–8 years The role", (4, 8)),
        ("Minimum 6-year experience working as Support Engineer", (6, None)),
        ("Relevant experience of 2 - 5 years with the similar industry", (2, 5)),
        ("Relevant experience for 2 to 4 years. Master’s in business", (2, 4)),
        ("14+ years of IT Expereince 1+ years of in Salesforce", (14, None)),
        ("Work experience: 8-10+ years in enterprise IT", (8, 10)),
        ("Key Skills: 3 to 10 yrs of experience Strong programming", (3, 10)),
        ("Exp: 0-2 yrs", (0, 2)),
        ("5-12 years of exp in SAP MM.", (5, 12)),
        ("Cyber experience ranging from 3 to 7 years is mandatory", (3, 7)),
        ("Minimum 7.5 year(s) of experience is required", (7, None)),  # Accenture
        ("8–12+ years of experience delivering infrastructure", (8, 12)),  # not 12: the range starts at 8
        ("5-6 + years of experience in data engineering", (5, 6)),
        ("Minimum 3.5 to 9.5 years of experience in relevant field", (3, 9)),
        ("Experience: 6-8 years Education: B.E- Electrical", (6, 8)),
        ("8 years and above of experience working with Workday", (8, None)),
        ("We are hiring freshers for our Chennai office", (0, 1)),
        ("Open to fresh graduates with a B.Tech", (0, 1)),
        ("This is an entry-level role", (0, 1)),
        ("Freshers welcome. 2+ years of Java experience preferred", (2, None)),  # a stated minimum wins
    ],
)
def test_extracts(html, want):
    got = extract_experience(html)
    assert got is not None and (got.min_years, got.max_years) == want


@pytest.mark.parametrize(
    "html",
    [
        "Educational Qualification : 15 years full time education",
        "- A 15 years full time education Experience is mandatory",
        "For over 25 years, Acme has been a leader in payments.",
        "With its strong over 55-year heritage, Capgemini is trusted by its clients",
        "We offer a 2 year warranty on all products.",
        "Experience the culture: 5 days a week in office",
        "Amgen helped establish the biotechnology industry more than 40 years ago and remains",
        "Founded over 145 years ago, the company has sustained a culture",
        "Nearly 30 years later, that question still fuels everything we do",
        "operating in 30 markets with 57 years of unbroken profitability",
        "Complementary Health screening for 35 yrs. and above",
        "Bosch Group is more than 139 years old organization",
        "Minimum Qualifications: Bachelors (12-15 years) or Master’s degree(10-15 years) in Computer Science",
        "You will mentor entry-level engineers and review designs",
        "Freshers need not apply",
        "For nearly 100 years, we’ve been helping customers build",
        "we have been innovating for 40 years in the payments industry",
    ],
)
def test_ignores(html):
    assert extract_experience(html) is None


@pytest.mark.parametrize(
    ("title", "want"),
    [
        ("Intern Bachelors Embedded Eng", (0, 1)),
        ("Graduate Engineer Trainee", (0, 1)),
        ("SDE-1", (0, 2)),
        ("Systems Engr I", (0, 2)),
        ("Associate Product Manager", (0, 2)),
        ("Software Engr II", (2, 5)),
        ("Assistant Manager – Business Analyst", (2, 5)),
        ("Product Manager", (2, 5)),
        ("Data Engineer III", (4, 8)),
        ("IN_Senior Associate_ Palantir", (5, None)),
        ("Sr. Analyst", (5, None)),
        ("Track Manager", (7, None)),
        ("Group Product Manager", (7, None)),
        ("Expert Model-Based Design (MBD) Engineer", (8, None)),
        ("Engineering Manager", (10, None)),
        ("Associate Director, Data", (12, None)),
        ("Software Engineer", None),
        ("Lead Generation Executive", None),
    ],
)
def test_estimates_from_the_title(title, want):
    got = estimate_experience(title)
    assert (got and (got.min_years, got.max_years)) == want


def test_scrape_reads_experience_from_the_qualifications_extra():
    from src.processing.cpu import _extract_experience_fields

    # Oracle HCM: the description is the company blurb; the years are in ExternalQualificationsStr.
    assert _extract_experience_fields("<p>About Kotak</p>", {"qualifications": "<li>5-8 years of experience</li>"}) == (5, 8)
    assert _extract_experience_fields("<p>About Kotak</p>", {"qualifications": ["1-2 years’ experience"]}) == (1, 2)
    assert _extract_experience_fields(None, None) == (None, None)
