"""
seed.py — Seed the OpenMNC MongoDB database with services and site_settings.

Usage:
    1. Copy .env.example to .env and fill in your MONGODB_URI and credentials.
    2. Run:  python seed.py
    3. The script will also print the bcrypt hash for ADMIN_PASSWORD.
       Copy that hash into your .env as ADMIN_PASSWORD_HASH.

Environment variable required: ADMIN_PASSWORD (plain text, only used at seed time)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/openmnc")
DB_NAME = "openmnc"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)

SERVICES = [
    {
        "slug": "business-automation",
        "title": "Business Automation & AI Integration",
        "tagline": "Multiply revenue. Eliminate manual work.",
        "description": (
            "At OpenMNC, we help businesses break free from the trap of repetitive, "
            "time-consuming manual operations. Our Business Automation & AI Integration "
            "service designs and deploys custom AI-driven workflows that handle the "
            "tasks your team shouldn't be doing — freeing them to focus on growth. "
            "Whether it's automating customer communications, integrating intelligent "
            "data pipelines, or embedding AI decision-making into your existing software "
            "stack, we tailor every solution to your business model. The result: "
            "measurable revenue multiplication, dramatically improved reliability, "
            "near-zero operational waste, and a competitive edge that is hard to replicate."
        ),
        "features": [
            "Custom AI workflow automation",
            "Revenue multiplication strategies",
            "Business process optimization",
            "AI integration consulting",
            "Reliability & uptime guarantee",
            "Zero time-waste operations",
        ],
        "icon": "automation",
        "order": 1,
        "is_active": True,
        "updated_at": NOW,
    },
    {
        "slug": "custom-development",
        "title": "Custom App & Software Development",
        "tagline": "From your idea to a living product.",
        "description": (
            "We transform visionary ideas into polished, production-ready digital products. "
            "Before writing a single line of code we conduct a deep requirement analysis — "
            "listening carefully to understand not just what you want to build, but why and "
            "for whom. From there our team handles full-cycle development: architecture, "
            "frontend, backend, QA, and deployment. We also cover App Store Optimization "
            "(ASO) to ensure your product gets discovered, plus marketing and ongoing "
            "maintenance so it keeps growing after launch. Whether you are a solopreneur "
            "with a napkin sketch or a startup ready to scale, we meet you where you are."
        ),
        "features": [
            "Deep requirement analysis",
            "Full-cycle development",
            "App Store Optimization (ASO)",
            "Marketing & growth support",
            "Ongoing maintenance",
            "Solopreneur & startup friendly",
        ],
        "icon": "code",
        "order": 2,
        "is_active": True,
        "updated_at": NOW,
    },
    {
        "slug": "inhouse-products",
        "title": "In-House Products & Games",
        "tagline": "Products we build, publish, and stand behind.",
        "description": (
            "OpenMNC doesn't just build for clients — we build for ourselves too. "
            "Our in-house product portfolio includes Kibo VPN (a privacy-first VPN tool), "
            "Calorie AI (an intelligent health and nutrition tracker), and CardSnap "
            "(smart digital business cards). We also develop mobile games and bespoke "
            "software products, all published on the Google Play Store and Apple App Store. "
            "Every in-house product is a living proof of our engineering capability and "
            "our commitment to shipping real, useful software."
        ),
        "features": [
            "Google Play & App Store published",
            "Kibo VPN - Privacy tool",
            "Calorie AI - Health tracker",
            "CardSnap - Smart business cards",
            "Custom game development",
            "Proprietary software R&D",
        ],
        "icon": "apps",
        "order": 3,
        "is_active": True,
        "updated_at": NOW,
    },
    {
        "slug": "social-media-management",
        "title": "Social Media Management & Organic Growth",
        "tagline": "Grow organically. No heavy ad spend.",
        "description": (
            "We provide end-to-end social media management for Instagram, Facebook, and "
            "YouTube, built entirely around organic growth — no bloated ad budgets required. "
            "Our process starts with deep niche research and algorithm matching so your "
            "content finds the right audience. We write high-retention scripts using our "
            "Hook → Engagement → Relativity → Reveal framework, edit your videos "
            "professionally, and craft captions and hashtag strategies that drive real "
            "engagement. All you have to do is record raw footage — we handle everything "
            "else, from post scheduling to performance analysis."
        ),
        "features": [
            "Instagram, Facebook & YouTube management",
            "High-retention scripting (Hook→Engage→Reveal)",
            "Video editing & optimization",
            "Hashtag & caption strategy",
            "Algorithm matching",
            "Niche-based content calendar",
        ],
        "icon": "social",
        "order": 4,
        "is_active": True,
        "updated_at": NOW,
    },
    {
        "slug": "student-guidance",
        "title": "Student Guidance & EdTech",
        "tagline": "Free career guidance. Real college savings.",
        "description": (
            "We believe every 12th-pass student deserves honest, unbiased guidance — "
            "regardless of their financial background. That's why our career and college "
            "consultation service is 100% free for students. We help young people align "
            "their interests and strengths with the right fields and institutions, cutting "
            "through the noise of misleading counselling. Through our partner college "
            "network, students can access subsidies ranging from ₹3,000 to ₹10,000 and "
            "industrial partnership discounts, making quality education genuinely accessible."
        ),
        "features": [
            "100% free consultation",
            "Partner college subsidies ₹3,000–₹10,000",
            "Field & career alignment",
            "Right college guidance",
            "Industrial partnership discounts",
            "Zero cost to students",
        ],
        "icon": "education",
        "order": 5,
        "is_active": True,
        "updated_at": NOW,
    },
    {
        "slug": "industrial-training",
        "title": "Advanced Industrial Training",
        "tagline": "Real projects. High-end tech. 3 months.",
        "description": (
            "Our 3-month Advanced Industrial Training programme is not a tutorial course — "
            "it is real production-level work on real projects. Trainees dive into Advanced "
            "IoT (Robotics, Drones, AI Smart Home systems), Web Development, and App "
            "Development under the mentorship of experienced engineers. Pricing starts at "
            "₹3,000–₹7,000, with additional subsidy offsets available for students referred "
            "through our partner colleges. By the time you finish, you have shipped actual "
            "projects you can show to employers — not certificates from Udemy."
        ),
        "features": [
            "Advanced IoT & Robotics",
            "Drone technology",
            "AI Smart Home systems",
            "Web & App Development",
            "₹3,000–₹7,000 pricing",
            "Subsidy offset for partner students",
        ],
        "icon": "training",
        "order": 6,
        "is_active": True,
        "updated_at": NOW,
    },
]

BLOGS = [
    {
        "slug": "turn-app-idea-into-reality",
        "title": "How Visionary Founders Turn App Ideas into Scalable Realities",
        "category": "B2B & Tech Solutions",
        "target_audience": "Founders & Solopreneurs",
        "excerpt": "A battle-tested blueprint for visionary solopreneurs: why deep requirement analysis beats jumping straight into code, and how to conquer development, maintenance, and App Store Optimization (ASO).",
        "content": """## From Napkin Sketch to Production App

Every month, hundreds of visionary entrepreneurs conceive transformative software and app ideas. But without the right technical roadmap, many fail before writing their first line of code.

### 1. Requirement Deep-Dive Before Code
The biggest mistake founders make is building based on assumptions. At OpenMNC, our discovery phase immerses our engineers in your business context, target audience psychology, and user retention loops.

### 2. Full-Cycle Engineering & Architecture
Your app must be built to scale smoothly from day one. Using modern frameworks (React, FastAPI, scalable databases), we build lean, secure MVPs that don't incur expensive server bills.

### 3. App Store Optimization (ASO) & Launch Marketing
Building the app is only 50% of the battle. The other 50% is discovery. We optimize keywords, icon psychology, and Google Play ranking factors so organic downloads start flowing immediately.

### 4. Continuous Iteration & Maintenance
Software is living infrastructure. We partner with founders on ongoing maintenance, bug fixes, and feature expansions as user feedback rolls in.""",
        "cover_image": "https://images.unsplash.com/photo-1551650975-87deedd944c3?auto=format&fit=crop&w=1200&q=80",
        "author_name": "Amit Barai",
        "author_role": "Founder & Director, OpenMNC LLP",
        "tags": ["App Development", "ASO", "Startup Advice", "Custom Software"],
        "target_service_slug": "custom-development",
        "cta_headline": "Have a custom app or software idea?",
        "cta_button_text": "Transform Your Idea into Reality with OpenMNC →",
        "meta_title": "How to Turn an App Idea into Reality | OpenMNC LLP",
        "meta_description": "Learn how OpenMNC helps visionary solopreneurs turn app ideas into reality with deep analysis, full-cycle development, and App Store Optimization.",
        "is_published": True,
        "views_count": 142,
        "created_at": NOW,
        "updated_at": NOW,
    },
    {
        "slug": "free-student-career-guidance-college-subsidy",
        "title": "100% Free Career Guidance for 12th-Pass Students: Save ₹3,000–₹10,000 in College Admissions",
        "category": "Student Guidance",
        "target_audience": "12th-Pass Students & Parents",
        "excerpt": "Navigating college admissions after 12th standard shouldn't be stressful or expensive. Discover how OpenMNC provides completely free career consultation and exclusive ₹3,000 to ₹10,000 partner college subsidies.",
        "content": """## Making Quality Higher Education Genuinely Accessible

Choosing the right career path and college after 12th grade is one of the most critical decisions in a student's life. Unfortunately, misleading consultants often charge high fees while pushing students toward suboptimal colleges.

### 1. 100% Free Career Guidance — Zero Hidden Costs
OpenMNC was built on the core belief that student guidance should never be commercialized. Our mentorship is completely free for all 12th-pass students. We evaluate:
- Personal strengths and natural aptitude
- Emerging technological fields (AI, IoT, Robotics, Data Science)
- Return on Investment (ROI) of degree programs

### 2. The ₹3,000 to ₹10,000 Partnership Subsidy
Because OpenMNC serves as an official industrial partner to accredited universities and colleges across India, we have secured direct institutional discounts. When students enroll through our partnership network, they receive between ₹3,000 and ₹10,000 off their college fees.

### 3. Real Project Industrial Training
Rather than sending students to expensive third-party training centers that charge ₹10,000–₹15,000 for basic tutorials, students can roll their subsidy into our 3-month advanced industrial training or receive the remaining funds back.""",
        "cover_image": "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=1200&q=80",
        "author_name": "Amit Barai",
        "author_role": "Founder & Director, OpenMNC LLP",
        "tags": ["Student Guidance", "College Admission", "Subsidies", "Career Counseling"],
        "target_service_slug": "student-guidance",
        "cta_headline": "Passed 12th or looking for the right college?",
        "cta_button_text": "Claim Your 100% Free Career Counseling & Subsidy →",
        "meta_title": "Free Career Guidance & College Subsidy for 12th Students | OpenMNC",
        "meta_description": "100% free career consultation for 12th-pass students in India. Save ₹3,000–₹10,000 in partner college admissions with OpenMNC industrial discounts.",
        "is_published": True,
        "views_count": 289,
        "created_at": NOW,
        "updated_at": NOW,
    },
    {
        "slug": "business-automation-ai-revenue-multiplier",
        "title": "Multiply Revenue by Automating Repetitive Tasks with Custom AI Workflows",
        "category": "B2B & Tech Solutions",
        "target_audience": "Business Owners & Founders",
        "excerpt": "How modern businesses eliminate 20+ hours of weekly manual work and boost profit margins through bespoke AI integrations and automated operational pipelines.",
        "content": """## Stop Wasting Time on Repetitive Operations

In traditional business workflows, high-value employees spend up to 40% of their working hours copying data, reconciling invoices, scheduling follow-ups, and managing basic customer queries.

### The AI Automation Advantage
By integrating tailored AI pipelines, OpenMNC helps enterprises:
- **Zero Latency Operations:** Automate repetitive data entry, CRM updates, and inventory tracking.
- **Intelligent Customer Routing:** AI agents that pre-qualify leads and route them to sales reps in real time.
- **Cost Reduction:** Drastically reduce operational overhead without adding bloated headcounts.""",
        "cover_image": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=80",
        "author_name": "Amit Barai",
        "author_role": "Founder & Director, OpenMNC LLP",
        "tags": ["AI Automation", "Business Efficiency", "Revenue Growth"],
        "target_service_slug": "business-automation",
        "cta_headline": "Ready to eliminate manual work and scale revenue?",
        "cta_button_text": "Request a Free AI Automation Audit →",
        "meta_title": "Business Automation & AI Integration | OpenMNC LLP",
        "meta_description": "Multiply revenue and eliminate repetitive tasks with custom AI solutions engineered by OpenMNC LLP.",
        "is_published": True,
        "views_count": 98,
        "created_at": NOW,
        "updated_at": NOW,
    },
]

CAREERS = [
    {
        "title": "Full-Stack AI Developer",
        "department": "Engineering",
        "location": "Remote, India",
        "type": "full-time",
        "experience_level": "Mid-Level",
        "salary_range": "₹6,00,000 - ₹12,00,000 / year",
        "description": "We are seeking a talented full-stack engineer passionate about building AI-first web applications, LLM agents, and scalable cloud APIs.",
        "responsibilities": [
            "Architect and build client web applications using React, Vite, and FastAPI",
            "Integrate OpenAI, Claude, and Gemini APIs into production pipelines",
            "Maintain MongoDB database models and optimize query speeds",
        ],
        "requirements": [
            "2+ years experience with React and Python (FastAPI/Django/Flask)",
            "Hands-on experience with RESTful APIs, Git, and Docker",
            "Understanding of AI prompting, embeddings, and vector stores",
        ],
        "benefits": [
            "100% remote flexibility",
            "Generous learning allowance for AI certifications",
            "Direct mentorship with founder Amit Barai",
        ],
        "is_active": True,
        "google_jobs_eligible": True,
        "posted_at": NOW,
        "updated_at": NOW,
    },
    {
        "title": "IoT & Robotics Trainer (Advanced)",
        "department": "EdTech & Training",
        "location": "Hybrid / Remote, India",
        "type": "full-time",
        "experience_level": "Mid-Senior",
        "salary_range": "₹5,00,000 - ₹9,00,000 / year",
        "description": "Lead our flagship 3-month industrial training program covering Drones, Robotics, and AI-enabled Smart Home systems.",
        "responsibilities": [
            "Mentor college students and trainees on real-world IoT hardware and microcontrollers",
            "Guide trainees through drone assembly, sensor fusion, and robotics programming",
            "Review student project deliverables and certify industry readiness",
        ],
        "requirements": [
            "Demonstrated experience in embedded systems, Arduino/ESP32/Raspberry Pi, and robotics",
            "Passion for practical, project-based teaching (no basic boring slides)",
            "Strong communication skills in Hindi and English",
        ],
        "benefits": [
            "Hardware lab stipend",
            "Performance bonuses on cohort success",
            "Flexible schedule",
        ],
        "is_active": True,
        "google_jobs_eligible": True,
        "posted_at": NOW,
        "updated_at": NOW,
    },
]

SITE_SETTINGS = [
    {"key": "hero_headline", "value": "We Build What You Envision", "section": "hero"},
    {
        "key": "hero_subheadline",
        "value": "AI-powered solutions, custom software, and organic growth for solopreneurs and visionary entrepreneurs.",
        "section": "hero",
    },
    {"key": "hero_cta_primary", "value": "Explore Our Services", "section": "hero"},
    {"key": "hero_cta_secondary", "value": "Get Free Consultation", "section": "hero"},
    {"key": "about_title", "value": "About OpenMNC LLP", "section": "about"},
    {
        "key": "about_description",
        "value": (
            "OpenMNC LLP is a technology and digital solutions company founded by Amit Barai. "
            "We help solopreneurs and visionary entrepreneurs transform their ideas into reality "
            "through AI automation, custom software development, social media management, and "
            "advanced industrial training."
        ),
        "section": "about",
    },
    {"key": "contact_email", "value": "hello@openmnc.com", "section": "contact"},
    {"key": "contact_phone", "value": "+91 8509684056", "section": "contact"},
    {"key": "contact_whatsapp", "value": "+91 8509684056", "section": "contact"},
    {"key": "contact_city", "value": "India", "section": "contact"},
    {"key": "founder_name", "value": "Amit Barai", "section": "about"},
    {"key": "founder_role", "value": "Founder & Director", "section": "about"},
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

async def seed():
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]

    print("=" * 60)
    print("OpenMNC Database Seeder")
    print("=" * 60)

    # --- Admin password hash ---
    if ADMIN_PASSWORD:
        hashed = pwd_context.hash(ADMIN_PASSWORD)
        print(f"\n[AUTH] Generated bcrypt hash for ADMIN_PASSWORD:")
        print(f"  ADMIN_PASSWORD_HASH={hashed}")
        print("  → Copy this into your .env file.\n")
    else:
        print(
            "\n[AUTH] ADMIN_PASSWORD env var not set. "
            "Set it and re-run to generate ADMIN_PASSWORD_HASH.\n"
        )

    # --- Services ---
    services_col = db["services"]
    seeded_services = 0
    skipped_services = 0
    for svc in SERVICES:
        existing = await services_col.find_one({"slug": svc["slug"]})
        if existing:
            print(f"[services] SKIP  — '{svc['slug']}' already exists")
            skipped_services += 1
        else:
            await services_col.insert_one(svc.copy())
            print(f"[services] SEEDED — '{svc['slug']}'")
            seeded_services += 1

    # Ensure index on slug
    await services_col.create_index("slug", unique=True)
    print(f"\n[services] Done: {seeded_services} seeded, {skipped_services} skipped.")

    # --- Site Settings ---
    settings_col = db["site_settings"]
    seeded_settings = 0
    skipped_settings = 0
    for setting in SITE_SETTINGS:
        existing = await settings_col.find_one({"key": setting["key"]})
        if existing:
            print(f"[settings] SKIP  — '{setting['key']}' already exists")
            skipped_settings += 1
        else:
            doc = {**setting, "updated_at": NOW}
            await settings_col.insert_one(doc)
            print(f"[settings] SEEDED — '{setting['key']}'")
            seeded_settings += 1

    await settings_col.create_index("key", unique=True)
    print(f"\n[settings] Done: {seeded_settings} seeded, {skipped_settings} skipped.")

    # --- Blogs ---
    blogs_col = db["blogs"]
    seeded_blogs = 0
    skipped_blogs = 0
    for blog in BLOGS:
        existing = await blogs_col.find_one({"slug": blog["slug"]})
        if existing:
            print(f"[blogs] SKIP  — '{blog['slug']}' already exists")
            skipped_blogs += 1
        else:
            await blogs_col.insert_one(blog.copy())
            print(f"[blogs] SEEDED — '{blog['slug']}'")
            seeded_blogs += 1
    await blogs_col.create_index("slug", unique=True)
    await blogs_col.create_index("category")
    print(f"\n[blogs] Done: {seeded_blogs} seeded, {skipped_blogs} skipped.")

    # --- Careers ---
    careers_col = db["careers"]
    seeded_careers = 0
    for job in CAREERS:
        existing = await careers_col.find_one({"title": job["title"]})
        if not existing:
            await careers_col.insert_one(job.copy())
            print(f"[careers] SEEDED — '{job['title']}'")
            seeded_careers += 1
    print(f"\n[careers] Done: {seeded_careers} seeded.")

    # --- Indexes for other collections ---
    await db["careers"].create_index("is_active")
    await db["contact_submissions"].create_index("submitted_at")
    await db["contact_submissions"].create_index("intent_tag")
    await db["job_applications"].create_index("candidate_email")
    await db["job_applications"].create_index("applied_at")

    client.close()
    print("\n[seed] All done. MongoDB connection closed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
