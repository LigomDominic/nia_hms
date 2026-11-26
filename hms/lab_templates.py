"""Library of standard laboratory tests and their structured result templates.

Each template is a list of analyte fields:
    {"n": field label, "u": unit, "r": reference range,
     "k": "num" | "text" | "sel", "o": options for "sel"}

A LabTest carries a `template` key; when the lab records a result the matching
template's fields are rendered and the entered values are stored as JSON on the
request item. Tests with no template keep the single free-text result box.
Microbiology tests keep the dedicated MCS sheet (template key "mcs" is a no-op).
"""


def F(name, unit="", ref="", k="num", options=None):
    return {"n": name, "u": unit, "r": ref, "k": k, "o": options or []}


def _sel_result(options):
    return {"n": "Result", "u": "", "r": "", "k": "sel", "o": options}


PN = ["Negative", "Positive"]          # qualitative pos/neg tests
RNR = ["Non-reactive", "Reactive"]     # serology titres
SEEN = ["Not seen", "Seen"]            # microscopy presence
SNR = ["Not seen", "+", "++", "+++"]   # semi-quantitative microscopy

RESULT_TEMPLATES = {
    # ---- Haematology ----
    "fbc": {"label": "Full Blood Count", "fields": [
        F("WBC", "x10^9/L", "4.0 - 11.0"), F("RBC", "x10^12/L", "4.5 - 5.5"),
        F("Haemoglobin", "g/dL", "12 - 16"), F("PCV / Hct", "%", "36 - 46"),
        F("MCV", "fL", "80 - 100"), F("MCH", "pg", "27 - 32"), F("MCHC", "g/dL", "32 - 36"),
        F("RDW", "%", "11.5 - 14.5"), F("Platelets", "x10^9/L", "150 - 450"),
        F("Neutrophils", "%", "40 - 70"), F("Lymphocytes", "%", "20 - 40"),
        F("Monocytes", "%", "2 - 8"), F("Eosinophils", "%", "1 - 4"), F("Basophils", "%", "0 - 1")]},
    "fbc_esr": {"label": "FBC + ESR", "fields": [
        F("WBC", "x10^9/L", "4.0 - 11.0"), F("RBC", "x10^12/L", "4.5 - 5.5"),
        F("Haemoglobin", "g/dL", "12 - 16"), F("PCV / Hct", "%", "36 - 46"),
        F("MCV", "fL", "80 - 100"), F("MCH", "pg", "27 - 32"), F("MCHC", "g/dL", "32 - 36"),
        F("Platelets", "x10^9/L", "150 - 450"), F("Neutrophils", "%", "40 - 70"),
        F("Lymphocytes", "%", "20 - 40"), F("Monocytes", "%", "2 - 8"),
        F("Eosinophils", "%", "1 - 4"), F("ESR", "mm/hr", "< 15")]},
    "pcv": {"label": "Packed Cell Volume", "fields": [F("PCV", "%", "36 - 46")]},
    "esr": {"label": "ESR", "fields": [F("ESR", "mm/hr", "0 - 15 (M) / 0 - 20 (F)")]},
    "retic": {"label": "Reticulocyte count", "fields": [F("Reticulocytes", "%", "0.5 - 2.5")]},
    "blood_group": {"label": "Blood Group & Rhesus", "fields": [
        F("ABO Group", k="sel", options=["A", "B", "AB", "O"]),
        F("Rhesus (D)", k="sel", options=["Positive", "Negative"])]},
    "genotype": {"label": "Haemoglobin Genotype", "fields": [
        F("Hb Genotype", k="sel", options=["AA", "AS", "AC", "SS", "SC", "CC"])]},
    "hb_electrophoresis": {"label": "Hb Electrophoresis", "fields": [
        F("HbA", "%", "95 - 98"), F("HbA2", "%", "2 - 3.5"), F("HbF", "%", "< 2"), F("HbS", "%", "0"),
        F("Interpretation", k="text")]},
    "sickling": {"label": "Sickling Test", "fields": [_sel_result(PN)]},
    "g6pd": {"label": "G6PD Screening", "fields": [
        _sel_result(["Normal", "Deficient"])]},
    "coombs": {"label": "Coombs Test", "fields": [_sel_result(PN)]},
    "pt": {"label": "Prothrombin Time", "fields": [
        F("PT", "secs", "11 - 13.5"), F("INR", "", "0.9 - 1.2"), F("Control", "secs", "")]},
    "aptt": {"label": "APTT", "fields": [
        F("APTT", "secs", "25 - 35"), F("Control", "secs", "")]},
    "bleeding_time": {"label": "Bleeding / Clotting Time", "fields": [
        F("Bleeding time", "mins", "2 - 7"), F("Clotting time", "mins", "5 - 10")]},
    "blood_film": {"label": "Peripheral Blood Film", "fields": [
        F("RBC morphology", k="text"), F("WBC morphology", k="text"),
        F("Platelets", k="text"), F("Parasites", k="sel", options=SEEN), F("Comment", k="text")]},
    "xmatch": {"label": "Cross-match", "fields": [
        F("Compatibility", k="sel", options=["Compatible", "Incompatible"]),
        F("Units matched", k="text")]},

    # ---- Clinical Chemistry ----
    "glucose": {"label": "Blood Glucose", "fields": [F("Glucose", "mg/dL", "70 - 110 (fasting)")]},
    "ogtt": {"label": "Oral Glucose Tolerance Test", "fields": [
        F("Fasting", "mg/dL", "70 - 110"), F("1 hour", "mg/dL", "< 180"),
        F("2 hours", "mg/dL", "< 140"), F("3 hour (optional)", "mg/dL", "")]},
    "hba1c": {"label": "HbA1c", "fields": [F("HbA1c", "%", "4.0 - 5.6")]},
    "lft": {"label": "Liver Function Test", "fields": [
        F("Total Bilirubin", "mg/dL", "0.3 - 1.2"), F("Direct Bilirubin", "mg/dL", "0.0 - 0.3"),
        F("Indirect Bilirubin", "mg/dL", "0.2 - 0.9"), F("AST (SGOT)", "U/L", "5 - 40"),
        F("ALT (SGPT)", "U/L", "5 - 41"), F("ALP", "U/L", "40 - 129"), F("GGT", "U/L", "8 - 61"),
        F("Total Protein", "g/dL", "6.4 - 8.3"), F("Albumin", "g/dL", "3.5 - 5.0"),
        F("Globulin", "g/dL", "2.0 - 3.5"), F("A/G Ratio", "", "1.1 - 2.2")]},
    "bilirubin": {"label": "Bilirubin", "fields": [
        F("Total Bilirubin", "mg/dL", "0.3 - 1.2"), F("Direct Bilirubin", "mg/dL", "0.0 - 0.3"),
        F("Indirect Bilirubin", "mg/dL", "0.2 - 0.9")]},
    "eucr": {"label": "Electrolytes, Urea & Creatinine", "fields": [
        F("Sodium", "mmol/L", "135 - 145"), F("Potassium", "mmol/L", "3.5 - 5.1"),
        F("Chloride", "mmol/L", "98 - 107"), F("Bicarbonate", "mmol/L", "22 - 29"),
        F("Urea", "mg/dL", "15 - 45"), F("Creatinine", "mg/dL", "0.6 - 1.3"),
        F("eGFR", "mL/min", "> 90")]},
    "electrolytes": {"label": "Serum Electrolytes", "fields": [
        F("Sodium", "mmol/L", "135 - 145"), F("Potassium", "mmol/L", "3.5 - 5.1"),
        F("Chloride", "mmol/L", "98 - 107"), F("Bicarbonate", "mmol/L", "22 - 29")]},
    "lipid": {"label": "Lipid Profile", "fields": [
        F("Total Cholesterol", "mg/dL", "< 200"), F("Triglycerides", "mg/dL", "< 150"),
        F("HDL", "mg/dL", "40 - 60"), F("LDL", "mg/dL", "< 130"), F("VLDL", "mg/dL", "10 - 40"),
        F("Chol/HDL Ratio", "", "< 5.0")]},
    "bone": {"label": "Bone Profile", "fields": [
        F("Calcium", "mg/dL", "8.5 - 10.5"), F("Phosphate", "mg/dL", "2.5 - 4.5"),
        F("Magnesium", "mg/dL", "1.7 - 2.4"), F("ALP", "U/L", "40 - 129")]},
    "protein": {"label": "Total Protein & Albumin", "fields": [
        F("Total Protein", "g/dL", "6.4 - 8.3"), F("Albumin", "g/dL", "3.5 - 5.0"),
        F("Globulin", "g/dL", "2.0 - 3.5"), F("A/G Ratio", "", "1.1 - 2.2")]},
    "cardiac": {"label": "Cardiac Enzymes", "fields": [
        F("CK Total", "U/L", "30 - 200"), F("CK-MB", "U/L", "< 25"),
        F("LDH", "U/L", "135 - 225"), F("AST (SGOT)", "U/L", "5 - 40")]},
    "troponin": {"label": "Troponin", "fields": [
        F("Troponin level", "ng/mL", "< 0.04"), _sel_result(PN)]},
    "iron": {"label": "Iron Studies", "fields": [
        F("Serum Iron", "ug/dL", "50 - 170"), F("TIBC", "ug/dL", "250 - 450"),
        F("Transferrin Saturation", "%", "20 - 50"), F("Ferritin", "ng/mL", "20 - 250")]},
    "csf_chem": {"label": "CSF Chemistry", "fields": [
        F("Appearance", k="sel", options=["Clear", "Cloudy", "Blood-stained", "Xanthochromic"]),
        F("Protein", "mg/dL", "15 - 45"), F("Glucose", "mg/dL", "50 - 80"),
        F("Chloride", "mmol/L", "116 - 122"), F("Cell count", "cells/mm3", "0 - 5")]},
    "fluid": {"label": "Body Fluid Analysis", "fields": [
        F("Appearance", k="text"), F("Protein", "g/dL", ""), F("Glucose", "mg/dL", ""),
        F("LDH", "U/L", ""), F("Cell count", "cells/mm3", ""), F("Comment", k="text")]},

    # ---- Single-analyte tests (unit & range shown from the test row) ----
    "single": {"label": "Single analyte", "fields": [F("Result")]},

    # ---- Serology & Immunology ----
    "serology": {"label": "Serology (Reactive/Non-reactive)", "fields": [
        _sel_result(RNR), F("Titre", k="text")]},
    "pos_neg": {"label": "Qualitative (Positive/Negative)", "fields": [_sel_result(PN)]},
    "igg_igm": {"label": "IgG / IgM", "fields": [
        F("IgG", k="sel", options=PN), F("IgM", k="sel", options=PN)]},
    "widal": {"label": "Widal (Typhoid titres)", "fields": [
        F("S. typhi O", "titre", "< 1:80", "text"), F("S. typhi H", "titre", "< 1:80", "text"),
        F("S. paratyphi A - O", "titre", "< 1:80", "text"), F("S. paratyphi A - H", "titre", "< 1:80", "text"),
        F("S. paratyphi B - O", "titre", "< 1:80", "text"), F("S. paratyphi B - H", "titre", "< 1:80", "text"),
        F("S. paratyphi C - O", "titre", "< 1:80", "text"), F("S. paratyphi C - H", "titre", "< 1:80", "text")]},
    "hep_b": {"label": "Hepatitis B Profile", "fields": [
        F("HBsAg", k="sel", options=PN), F("Anti-HBs", k="sel", options=PN),
        F("HBeAg", k="sel", options=PN), F("Anti-HBe", k="sel", options=PN),
        F("Anti-HBc", k="sel", options=PN)]},
    "psa": {"label": "Prostate Specific Antigen", "fields": [
        F("Total PSA", "ng/mL", "< 4.0"), F("Free PSA", "ng/mL", ""), F("Free/Total Ratio", "%", "> 25")]},
    "mantoux": {"label": "Mantoux / Tuberculin", "fields": [
        F("Induration", "mm", ""), _sel_result(PN)]},
    "cd4": {"label": "CD4 Count", "fields": [
        F("CD4 count", "cells/uL", "500 - 1500"), F("CD4 %", "%", "32 - 62")]},

    # ---- Parasitology ----
    "malaria_mp": {"label": "Malaria Parasite (smear)", "fields": [
        F("Malaria parasite", k="sel", options=SEEN),
        F("Species", k="sel", options=["P. falciparum", "P. vivax", "P. ovale", "P. malariae", "Mixed"]),
        F("Density", k="sel", options=["+", "++", "+++", "++++"])]},
    "microfilaria": {"label": "Microfilaria", "fields": [_sel_result(SEEN)]},
    "stool": {"label": "Stool Analysis", "fields": [
        F("Colour", k="text"), F("Consistency", k="sel",
                                 options=["Formed", "Semi-formed", "Loose", "Watery"]),
        F("Mucus", k="sel", options=["Absent", "Present"]),
        F("Occult blood", k="sel", options=PN), F("Pus cells", "/HPF", "", "text"),
        F("RBC", "/HPF", "", "text"), F("Ova / Cysts", "", "Not seen", "text"),
        F("Trophozoites", "", "Not seen", "text"), F("Other findings", k="text")]},
    "afb": {"label": "AFB (Ziehl-Neelsen)", "fields": [_sel_result(SNR)]},

    # ---- Urinalysis / CSF / Semen ----
    "urine": {"label": "Urinalysis", "fields": [
        F("Colour", k="sel", options=["Straw", "Yellow", "Amber", "Red", "Brown", "Colourless"]),
        F("Appearance", k="sel", options=["Clear", "Slightly cloudy", "Cloudy", "Turbid"]),
        F("pH", "", "4.6 - 8.0"), F("Specific Gravity", "", "1.005 - 1.030"),
        F("Protein", k="sel", options=["Negative", "Trace", "+", "++", "+++"]),
        F("Glucose", k="sel", options=["Negative", "Trace", "+", "++", "+++"]),
        F("Ketones", k="sel", options=["Negative", "Trace", "+", "++"]),
        F("Blood", k="sel", options=["Negative", "Trace", "+", "++", "+++"]),
        F("Bilirubin", k="sel", options=PN), F("Urobilinogen", k="sel", options=["Normal", "Increased"]),
        F("Nitrite", k="sel", options=PN), F("Leukocyte esterase", k="sel", options=["Negative", "Trace", "+", "++"]),
        F("Pus cells", "/HPF", "", "text"), F("RBC", "/HPF", "", "text"),
        F("Epithelial cells", "/HPF", "", "text"), F("Casts", "", "", "text"),
        F("Crystals", "", "", "text"), F("Yeast cells", k="sel", options=SEEN),
        F("Bacteria", k="sel", options=SEEN)]},
    "urine24": {"label": "24-Hour Urine", "fields": [
        F("Total volume", "mL", ""), F("Protein excretion", "g/24h", "< 0.15"),
        F("Creatinine clearance", "mL/min", "90 - 140")]},
    "semen": {"label": "Semen Analysis", "fields": [
        F("Volume", "mL", ">= 1.5"), F("Colour", k="text"),
        F("Liquefaction time", "mins", "< 60"), F("pH", "", "7.2 - 8.0"),
        F("Concentration", "M/mL", ">= 15"), F("Total motility", "%", ">= 40"),
        F("Progressive motility", "%", ">= 32"), F("Non-progressive", "%", ""),
        F("Immotile", "%", ""), F("Normal morphology", "%", ">= 4"),
        F("Vitality", "%", ">= 58"), F("Pus cells", "/HPF", "", "text"), F("Comment", k="text")]},
    "csf": {"label": "CSF Analysis", "fields": [
        F("Appearance", k="sel", options=["Clear", "Cloudy", "Blood-stained", "Xanthochromic"]),
        F("WBC", "cells/mm3", "0 - 5"), F("RBC", "cells/mm3", "0"),
        F("Protein", "mg/dL", "15 - 45"), F("Glucose", "mg/dL", "50 - 80"),
        F("Gram stain", k="text"), F("ZN (AFB)", k="sel", options=["Not seen", "Seen"])]},
    "pcr": {"label": "Molecular / PCR", "fields": [
        F("Result", k="sel", options=["Detected", "Not detected"]),
        F("Viral load / copies", "copies/mL", "", "text"), F("Ct value", "", "", "text")]},
    "genexpert": {"label": "GeneXpert MTB/RIF", "fields": [
        F("MTB", k="sel", options=["Detected", "Not detected", "Trace"]),
        F("Rifampicin resistance", k="sel", options=["Not detected", "Detected", "Indeterminate"])]},
}


# name, category, sample, price, template key (None = plain free-text / MCS sheet)
TEST_LIBRARY = [
    # Haematology
    ("Full Blood Count (FBC)", "Haematology", "Blood", 4500, "fbc"),
    ("FBC + ESR", "Haematology", "Blood", 5500, "fbc_esr"),
    ("Packed Cell Volume (PCV)", "Haematology", "Blood", 1000, "pcv"),
    ("ESR", "Haematology", "Blood", 1500, "esr"),
    ("Reticulocyte Count", "Haematology", "Blood", 2500, "retic"),
    ("Blood Grouping & Rhesus", "Haematology", "Blood", 1500, "blood_group"),
    ("Genotype", "Haematology", "Blood", 2000, "genotype"),
    ("Haemoglobin Electrophoresis", "Haematology", "Blood", 6000, "hb_electrophoresis"),
    ("Sickling Test", "Haematology", "Blood", 1500, "sickling"),
    ("G6PD Screening", "Haematology", "Blood", 3000, "g6pd"),
    ("Prothrombin Time (PT/INR)", "Haematology", "Blood", 3500, "pt"),
    ("APTT", "Haematology", "Blood", 3500, "aptt"),
    ("Bleeding & Clotting Time", "Haematology", "Blood", 1500, "bleeding_time"),
    ("Peripheral Blood Film", "Haematology", "Blood", 3000, "blood_film"),
    ("Direct Coombs Test", "Haematology", "Blood", 3000, "coombs"),
    ("Indirect Coombs Test", "Haematology", "Blood", 3000, "coombs"),
    ("Cross-match", "Blood Bank", "Blood", 5000, "xmatch"),
    ("Antibody Screen", "Blood Bank", "Blood", 5000, "pos_neg"),

    # Clinical Chemistry
    ("Fasting Blood Sugar", "Clinical Chemistry", "Blood", 1500, "glucose"),
    ("Random Blood Sugar", "Clinical Chemistry", "Blood", 1500, "glucose"),
    ("2-Hour Postprandial Sugar", "Clinical Chemistry", "Blood", 1500, "glucose"),
    ("Oral Glucose Tolerance Test (OGTT)", "Clinical Chemistry", "Blood", 4000, "ogtt"),
    ("HbA1c (Glycated Haemoglobin)", "Clinical Chemistry", "Blood", 5000, "hba1c"),
    ("Liver Function Test (LFT)", "Clinical Chemistry", "Blood", 9000, "lft"),
    ("Kidney Function Test (E/U/Cr)", "Clinical Chemistry", "Blood", 8000, "eucr"),
    ("Serum Electrolytes", "Clinical Chemistry", "Blood", 5000, "electrolytes"),
    ("Serum Urea", "Clinical Chemistry", "Blood", 2000, "single"),
    ("Serum Creatinine", "Clinical Chemistry", "Blood", 2000, "single"),
    ("Lipid Profile", "Clinical Chemistry", "Blood", 8000, "lipid"),
    ("Uric Acid", "Clinical Chemistry", "Blood", 2500, "single"),
    ("Serum Calcium", "Clinical Chemistry", "Blood", 2500, "single"),
    ("Serum Magnesium", "Clinical Chemistry", "Blood", 2500, "single"),
    ("Serum Phosphate", "Clinical Chemistry", "Blood", 2500, "single"),
    ("Bone Profile", "Clinical Chemistry", "Blood", 7000, "bone"),
    ("Total Protein & Albumin", "Clinical Chemistry", "Blood", 3500, "protein"),
    ("Serum Bilirubin (Total & Direct)", "Clinical Chemistry", "Blood", 3000, "bilirubin"),
    ("Cardiac Enzymes", "Clinical Chemistry", "Blood", 9000, "cardiac"),
    ("Troponin I", "Clinical Chemistry", "Blood", 6000, "troponin"),
    ("Troponin T", "Clinical Chemistry", "Blood", 6000, "troponin"),
    ("Serum Amylase", "Clinical Chemistry", "Blood", 3000, "single"),
    ("Serum Lipase", "Clinical Chemistry", "Blood", 3500, "single"),
    ("C-Reactive Protein (CRP)", "Clinical Chemistry", "Blood", 3500, "single"),
    ("Procalcitonin", "Clinical Chemistry", "Blood", 8000, "single"),
    ("D-Dimer", "Clinical Chemistry", "Blood", 7000, "single"),
    ("Ferritin", "Clinical Chemistry", "Blood", 6000, "single"),
    ("Iron Studies", "Clinical Chemistry", "Blood", 9000, "iron"),
    ("Vitamin B12", "Clinical Chemistry", "Blood", 8000, "single"),
    ("Folate", "Clinical Chemistry", "Blood", 7000, "single"),
    ("Vitamin D (25-OH)", "Clinical Chemistry", "Blood", 10000, "single"),
    ("Acid Phosphatase", "Clinical Chemistry", "Blood", 4000, "single"),
    ("CSF Chemistry", "Clinical Chemistry", "CSF", 5000, "csf_chem"),
    ("Ascitic Fluid Analysis", "Clinical Chemistry", "Ascitic fluid", 5000, "fluid"),
    ("Pleural Fluid Analysis", "Clinical Chemistry", "Pleural fluid", 5000, "fluid"),

    # Serology & Immunology
    ("HIV Screening (1 & 2)", "Serology", "Blood", 2500, "serology"),
    ("HIV Screening", "Serology", "Blood", 2500, "serology"),
    ("HBsAg", "Serology", "Blood", 2500, "serology"),
    ("Anti-HCV", "Serology", "Blood", 3000, "serology"),
    ("Hepatitis A IgM", "Serology", "Blood", 4500, "serology"),
    ("HBeAg", "Serology", "Blood", 4000, "serology"),
    ("Hepatitis B Profile", "Serology", "Blood", 10000, "hep_b"),
    ("VDRL / RPR (Syphilis)", "Serology", "Blood", 2500, "serology"),
    ("TPHA", "Serology", "Blood", 4000, "serology"),
    ("H. Pylori Antibody", "Serology", "Blood", 3000, "serology"),
    ("H. Pylori Stool Antigen", "Serology", "Stool", 3500, "pos_neg"),
    ("Widal Test", "Serology", "Blood", 2000, "widal"),
    ("Typhoid IgG / IgM", "Serology", "Blood", 3500, "igg_igm"),
    ("Rheumatoid Factor (RF)", "Immunology", "Blood", 3500, "serology"),
    ("ASO Titre", "Immunology", "Blood", 4000, "single"),
    ("Chlamydia IgG / IgM", "Immunology", "Blood", 6000, "igg_igm"),
    ("Rubella IgG / IgM", "Immunology", "Blood", 6000, "igg_igm"),
    ("CMV IgG / IgM", "Immunology", "Blood", 6000, "igg_igm"),
    ("Toxoplasma IgG / IgM", "Immunology", "Blood", 6000, "igg_igm"),
    ("HSV 1 & 2 IgG / IgM", "Immunology", "Blood", 7000, "igg_igm"),
    ("PSA (Total)", "Immunology", "Blood", 6000, "psa"),
    ("Free PSA", "Immunology", "Blood", 6000, "single"),
    ("CEA", "Immunology", "Blood", 7000, "single"),
    ("CA-125", "Immunology", "Blood", 8000, "single"),
    ("CA 15-3", "Immunology", "Blood", 8000, "single"),
    ("CA 19-9", "Immunology", "Blood", 8000, "single"),
    ("Alpha-fetoprotein (AFP)", "Immunology", "Blood", 7000, "single"),
    ("Beta-hCG (Quantitative)", "Immunology", "Blood", 4000, "single"),
    ("Dengue NS1 Antigen", "Immunology", "Blood", 5000, "pos_neg"),
    ("Dengue IgG / IgM", "Immunology", "Blood", 6000, "igg_igm"),
    ("COVID-19 Antigen", "Immunology", "Blood", 5000, "pos_neg"),
    ("CD4 Count", "Immunology", "Blood", 6000, "cd4"),
    ("HIV Viral Load", "Immunology", "Blood", 20000, "single"),
    ("EBV IgM", "Immunology", "Blood", 6000, "serology"),
    ("Brucella Agglutination", "Immunology", "Blood", 4000, "serology"),
    ("Mantoux (Tuberculin) Test", "Immunology", "Skin", 2500, "mantoux"),

    # Endocrinology
    ("Thyroid Function Test (T3, T4, TSH)", "Endocrinology", "Blood", 10000, "tft"),
    ("Free T3", "Endocrinology", "Blood", 4500, "single"),
    ("Free T4", "Endocrinology", "Blood", 4500, "single"),
    ("TSH", "Endocrinology", "Blood", 4500, "single"),
    ("FSH", "Endocrinology", "Blood", 5000, "single"),
    ("LH", "Endocrinology", "Blood", 5000, "single"),
    ("Prolactin", "Endocrinology", "Blood", 5000, "single"),
    ("Estradiol (E2)", "Endocrinology", "Blood", 5500, "single"),
    ("Progesterone", "Endocrinology", "Blood", 5500, "single"),
    ("Testosterone", "Endocrinology", "Blood", 5500, "single"),
    ("Cortisol", "Endocrinology", "Blood", 6000, "single"),
    ("Fasting Insulin", "Endocrinology", "Blood", 6000, "single"),
    ("Fertility Hormone Profile", "Endocrinology", "Blood", 15000, "hormones"),

    # Parasitology
    ("Malaria Parasite (MP)", "Parasitology", "Blood", 1500, "malaria_mp"),
    ("Malaria RDT", "Parasitology", "Blood", 1200, "pos_neg"),
    ("Microfilaria", "Parasitology", "Blood", 3000, "microfilaria"),
    ("Stool Microscopy", "Parasitology", "Stool", 1500, "stool"),
    ("Stool Occult Blood", "Parasitology", "Stool", 1500, "pos_neg"),
    ("Sputum AFB (ZN)", "Parasitology", "Sputum", 2000, "afb"),
    ("Skin Snip", "Parasitology", "Skin", 4000, "pos_neg"),

    # Urinalysis
    ("Urinalysis", "Urinalysis", "Urine", 1500, "urine"),
    ("Pregnancy Test (Urine)", "Urinalysis", "Urine", 1000, "pos_neg"),
    ("Pregnancy Test (Blood)", "Urinalysis", "Blood", 1500, "pos_neg"),
    ("24-Hour Urine Protein", "Urinalysis", "Urine (24h)", 4000, "urine24"),
    ("Bence Jones Protein", "Urinalysis", "Urine", 3500, "pos_neg"),

    # Semen / CSF
    ("Semen Analysis", "Special Tests", "Semen", 4500, "semen"),
    ("CSF Analysis", "Special Tests", "CSF", 5000, "csf"),

    # Microbiology (MCS sheet)
    ("Urine MCS", "Microbiology", "Urine", 4000, None),
    ("Stool MCS", "Microbiology", "Stool", 4000, None),
    ("Blood Culture", "Microbiology", "Blood", 6000, None),
    ("Throat Swab MCS", "Microbiology", "Throat swab", 4000, None),
    ("High Vaginal Swab (HVS) MCS", "Microbiology", "HVS", 4500, None),
    ("Urethral Swab MCS", "Microbiology", "Urethral swab", 4000, None),
    ("Wound Swab MCS", "Microbiology", "Wound swab", 4000, None),
    ("Sputum MCS", "Microbiology", "Sputum", 4000, None),
    ("Semen MCS", "Microbiology", "Semen", 4500, None),
    ("Ear Swab MCS", "Microbiology", "Ear swab", 4000, None),
    ("Eye Swab MCS", "Microbiology", "Eye swab", 4000, None),
    ("Endocervical Swab MCS", "Microbiology", "Endocervical swab", 4500, None),
    ("CSF MCS", "Microbiology", "CSF", 5500, None),

    # Molecular / PCR
    ("HBV DNA (PCR)", "Molecular / PCR", "Blood", 25000, "pcr"),
    ("HCV RNA (PCR)", "Molecular / PCR", "Blood", 25000, "pcr"),
    ("HIV RNA (PCR)", "Molecular / PCR", "Blood", 25000, "pcr"),
    ("COVID-19 PCR", "Molecular / PCR", "Nasopharyngeal swab", 15000, "pcr"),
    ("HPV DNA (PCR)", "Molecular / PCR", "Cervical swab", 20000, "pcr"),
    ("Chlamydia PCR", "Molecular / PCR", "Swab", 15000, "pcr"),
    ("Gonorrhoea PCR", "Molecular / PCR", "Swab", 15000, "pcr"),
    ("TB GeneXpert (MTB/RIF)", "Molecular / PCR", "Sputum", 12000, "genexpert"),
]

RESULT_TEMPLATES["tft"] = {"label": "Thyroid Function", "fields": [
    F("TSH", "uIU/mL", "0.27 - 4.2"), F("T4", "ng/dL", "5.1 - 14.1"),
    F("T3", "ng/mL", "0.8 - 2.0")]}

RESULT_TEMPLATES["hormones"] = {"label": "Fertility Hormone Profile", "fields": [
    F("FSH", "mIU/mL", ""), F("LH", "mIU/mL", ""), F("Prolactin", "ng/mL", ""),
    F("Estradiol", "pg/mL", ""), F("Progesterone", "ng/mL", ""), F("Testosterone", "ng/dL", "")]}

LIBRARY_TEMPLATE_BY_NAME = {name: tpl for name, _c, _s, _p, tpl in TEST_LIBRARY if tpl}


def template_for(key):
    return RESULT_TEMPLATES.get(key or "")


def install_library():
    """Insert every library test that isn't already in the LabTest catalog.

    Returns (added, updated, skipped): existing rows are untouched except that a
    missing template key is filled in from the library (so seeded tests pick up
    their structured form without touching prices or active flags).
    """
    from .extensions import db
    from .models import LabTest

    added = updated = 0
    skipped = []
    for name, category, sample, price, tpl in TEST_LIBRARY:
        test = LabTest.query.filter(db.func.lower(LabTest.name) == name.lower()).first()
        if test is None:
            db.session.add(LabTest(name=name, category=category, sample_type=sample,
                                   price=price, template=tpl, is_active=True))
            added += 1
        else:
            skipped.append(name)
            if tpl and not test.template:
                test.template = tpl
                updated += 1
    db.session.commit()
    return added, updated, skipped
