"""Demonstration leads.  NOTE: no scores are stored here; every score is computed by the engine."""

RAHUL_SHARMA = dict(
    name="Rahul Sharma", company_name="ABC Technologies", website="www.abctechnologies.com",
    job_title="Founder", industry="IT Services", company_location="Bangalore",
    company_size="50–100 Employees", lead_source="Website",
    requirement="Looking for CRM software", email="rahul@example.com", phone="+91 9876543210")

SYNTHETIC_LEADS = [
    # High potential
    dict(name="Priya Nair", company_name="FinEdge Solutions", website="finedge.io", job_title="CEO",
         industry="Fintech", company_location="Mumbai", company_size="100-250", lead_source="Referral",
         requirement="Need to replace our CRM and implement lead automation this quarter, budget approved",
         email="priya@finedge.io", phone="9820012345"),
    dict(name="Arjun Mehta", company_name="UrbanNest Realty", website="https://urbannestrealty.in",
         job_title="Managing Director", industry="Real Estate", company_location="Hyderabad",
         company_size="51-200", lead_source="Demo Request",
         requirement="Looking to buy a CRM with WhatsApp integration urgently",
         email="arjun@urbannestrealty.in", phone="+91 9848011223"),
    # Medium potential
    dict(name="Sneha Reddy", company_name="BrightPath Learning", website="brightpathlearning.com",
         job_title="Marketing Manager", industry="Education", company_location="Chennai",
         company_size="20-50", lead_source="Webinar", requirement="Exploring lead management tools for admissions",
         email="sneha@brightpathlearning.com", phone="+91 9444012345"),
    dict(name="Vikram Singh", company_name="SteelCraft Industries", website="steelcraft.co.in",
         job_title="Operations Manager", industry="Manufacturing", company_location="Pune",
         company_size="500-1000", lead_source="LinkedIn", requirement="Need an ERP system for inventory",
         email="vikram@steelcraft.co.in", phone="+91 9890012345"),
    dict(name="Kavya Iyer", company_name="GreenLeaf Retail", job_title="Team Lead", industry="Retail",
         company_location="Kochi", company_size="10-50", lead_source="Email Campaign",
         requirement="Interested in billing software", email="kavya@gmail.com"),
    # Low potential
    dict(name="Rohit Verma", company_name="Self", job_title="Student", industry="Education",
         lead_source="Cold Call", requirement="Just looking for a college project on CRM",
         email="rohit.v@gmail.com", phone="9000011122"),
    dict(name="Anita Das", company_name="Das Handicrafts", job_title="Sales Executive",
         industry="Handicrafts", company_size="1-10", lead_source="Purchased List",
         requirement="Not interested", email="anita@dashandicrafts.in"),
    # Incomplete / invalid
    dict(name="Mohan Kumar", company_name="Kumar & Sons", job_title="Owner", phone="12345"),
    dict(name="Deepa Joshi", email="deepa.joshi@@broken", requirement="Need CRM", lead_source="Website"),
    dict(company_name="Nova Logistics", website="not a website", industry="Logistics",
         company_size="lots", requirement="Looking for fleet management software",
         email="ops@novalogistics.com", phone="+91 9700012345", lead_source="Referral"),
    # Different industries / titles / requirements
    dict(name="Dr. Meera Pillai", company_name="CarePlus Clinics", website="careplusclinics.in",
         job_title="Director", industry="Healthcare", company_location="Bangalore",
         company_size="100-250", lead_source="Partner", requirement="Require patient management software and appointment automation",
         email="meera@careplusclinics.in", phone="+91 9886012345"),
    dict(name="Sam Carter", company_name="Brightline Media", website="brightline.media",
         job_title="VP Marketing", industry="Advertising", company_location="Delhi",
         company_size="250-500", lead_source="Trade Show", requirement="Evaluating marketing automation platforms next month",
         email="sam@brightline.media", phone="+1 415 555 2671"),
]
