# AdaptTable v1.3 – Raw + Expansion Test
# 🗓️ Mar 30, 12:57 PM | ✅ Working
# Added: Scrollable record, expansion in RDN summary
# Fixed: Duplicate display in patient view

import streamlit as st
from openai import OpenAI
import base64
import requests
import streamlit.components.v1 as components

import os
import json
from datetime import datetime
import streamlit as st

# 🧪 Test Mode Flag
TEST_MODE = True  # Set to False when you're running the actual pilot

# 📁 Session ID: unique timestamped folder per session
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_ID = f"HH_test_{timestamp}" if TEST_MODE else f"HH_live_{timestamp}"

# 📂 File save paths
BASE_PATH = "saved_outputs/sandbox_sessions" if TEST_MODE else "saved_outputs/pilot_sessions"
SESSION_FOLDER = os.path.join(BASE_PATH, SESSION_ID)

# 🔨 Create session folder if it doesn't exist
os.makedirs(SESSION_FOLDER, exist_ok=True)

# 🧾 Optional display for confirmation
st.caption(f"🔧 Test Mode Active — Saving session data to: `{SESSION_FOLDER}`")

# 🔍 TEST SAVE – delete after verifying it works
test_data = {"test": "file save check", "session_id": SESSION_ID}
save_json(test_data, "test_file.json")


# 🔄 Save any data dictionary to JSON
def save_json(data, filename):
    full_path = os.path.join(SESSION_FOLDER, filename)
    with open(full_path, "w") as f:
        json.dump(data, f, indent=2)


# --- API Keys ---
GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Helper Function: Extract all store blocks from markdown table ---
def extract_all_store_blocks(parsed_text):
    blocks = []
    current_store = None
    current_items = []

    for line in parsed_text.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("store name:"):
            if current_store and current_items:
                blocks.append((current_store, "\n".join(current_items)))
                current_items = []
            current_store = line.split(":", 1)[-1].strip()

        elif line.startswith("| Raw Item"):
            continue  # skip header
        elif line.startswith("|") and current_store:
            parts = line.split("|")
            if len(parts) > 2:
                raw = parts[1].strip()
                if raw.lower() != "raw item":
                    current_items.append(raw)
        elif not line and current_store and current_items:
            blocks.append((current_store, "\n".join(current_items)))
            current_store = None
            current_items = []

    # Catch final block
    if current_store and current_items:
        blocks.append((current_store, "\n".join(current_items)))

    return blocks


# --- Styled Logo Header ---
st.markdown(
    "<h1 style='font-family: Poppins, sans-serif; color: rgb(37,36,131); font-size: 2.5rem;'>AdaptTable</h1>",
    unsafe_allow_html=True
)

# --- Welcome Message ---
st.markdown("""
#### 👋 Welcome to AdaptTable – your household health co-pilot.

I’m here to help you meet your family’s health goals through smarter, easier food choices.

To get started, I’ll take a look at your recent grocery receipts. This helps me understand your household’s food habits so I can tailor guidance to your family’s needs.
""")

# --- Role-Based Access (Hybrid: URL + Password) ---
from urllib.parse import parse_qs

query_params = st.query_params
user_role = query_params.get("role", "patient")

# Optional Enhancement
if "last_user_role" in st.session_state and st.session_state.last_user_role != user_role:
    st.session_state.uploaded_receipts = []
st.session_state.last_user_role = user_role

st.markdown(f"🔍 **Current user role detected:** `{user_role}`")


if user_role == "provider":
    password = st.text_input("Enter provider access code:", type="password")
    if password != "rdn2024":
        st.warning("Access denied. Please enter the correct provider code.")
        st.stop()

# --- Session State for Multi-Upload ---
if "uploaded_receipts" not in st.session_state:
    st.session_state.uploaded_receipts = []

# --- Upload UI ---
new_receipt = st.file_uploader("Upload your grocery receipt image", type=["jpg", "jpeg", "png"])

if new_receipt is not None:
    if new_receipt.name not in [f.name for f in st.session_state.uploaded_receipts]:
        st.session_state.uploaded_receipts.append(new_receipt)
        st.success("Receipt uploaded!")
    else:
        st.warning("This receipt has already been uploaded.")

# --- Show Receipt Count ---
if st.session_state.uploaded_receipts:
    st.markdown(f"📥 **{len(st.session_state.uploaded_receipts)} receipt(s) uploaded:**")
    for file in st.session_state.uploaded_receipts:
        st.markdown(f"- {file.name}")

    # --- Conversational Prompt ---
    st.markdown("**I’ve scanned and structured your shopping data.**")
    
    st.markdown("""
    Would you like to upload more receipts so I can get the full picture of your household's food habits?
    
    You can use the upload box above to add more receipts.
    """)
    
    proceed = st.button("✅ I'm Ready – Analyze My Shopping Data")


else:
    proceed = False


# --- Combined Text Extraction and Analysis ---
if proceed:
    combined_text = ""

    for uploaded_file in st.session_state.uploaded_receipts:
        uploaded_file.seek(0)  # ✅ Reset file pointer
        image_content = uploaded_file.read()
        image_base64 = base64.b64encode(image_content).decode("utf-8")

        vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        vision_payload = {
            "requests": [{
                "image": {"content": image_base64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_response = requests.post(vision_url, json=vision_payload)
        result = vision_response.json()

        if (
            isinstance(result, dict) and
            "responses" in result and
            isinstance(result["responses"], list) and
            len(result["responses"]) > 0 and
            "fullTextAnnotation" in result["responses"][0]
        ):
            extracted_text = result["responses"][0]["fullTextAnnotation"]["text"]
            combined_text += extracted_text + "\n\n"
        else:
            st.error(f"Could not process: {uploaded_file.name}. Please check image quality.")
            st.stop()

    # --- Show All Raw Combined Text ---
    st.text_area("📝 Combined Receipt Text", combined_text, height=250)

    with st.spinner("⏳ Analyzing your grocery receipts... This may take 20–30 seconds."):
        try:
            st.subheader("Generating Master Shopping Record...")

            system_prompt_receipt_parser = """

            You are an expert receipt parser. Your role is to extract and expand grocery items from OCR-processed receipts using consistent formatting and practical product knowledge.

            You will be provided with:
            - The name of the store (e.g., Walmart)
            - A full list of extracted receipt text
            
            Your job:
            - Extract the raw item names exactly as written
            - Use your knowledge of common grocery products, retail item formats, and the store context to expand abbreviated names
            
            ### Output Format
            Return your output as a markdown table with two columns:
            | Raw Item | Expansion |
            
            Formatting Rules:
            - List every item in order. Include the original item name as-is under “Raw Item.”
            - Use the “Expansion” column to rewrite the full product name if you can confidently infer it from:
              - Common abbreviations (e.g., “GV SHP SH” → “Great Value Sharp Shredded Cheddar”)
              - Known store-brand items (e.g., Walmart’s Great Value)
              - Household or grocery items (e.g., “POPCRN” → “Popcorn”, “HP JUICE” → “High Pulp Juice”)
              - Product codes or sizes when common (e.g., “1.62Z KA LIQ” → “1.62 oz Kool-Aid Liquid”)
            - If the item is unclear or unknown, mark the Expansion as `Ambiguous`
            
            Do not:
            - Skip items
            - Remove duplicates
            - Guess fictional products
            - Reorganize or reclassify
            - Add a third column or commentary
            
            If the receipt includes a store name, use it to inform what types of products are likely to appear.
            
            You may expand even without 100% certainty when:
            - The expansion is widely accepted/common at that store
            - The abbreviation closely matches a well-known grocery item
            - The context is strong enough (e.g., surrounded by other dairy items)


            """


            user_prompt_receipt_parser = f"""
          
            Extract the store name, date, and all receipt items from the text below. 
            Follow the format:
            
            Store Name: [Store Name]  
            Date: [Date]  
            
            | Raw Item | Expansion |
            |----------|-----------|
            | ITEM A   | Expansion |
            | ITEM B   | Ambiguous |
            
            Extracted Receipt Text:
            {combined_text}
            """

    

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt_receipt_parser},
                    {"role": "user", "content": user_prompt_receipt_parser}
                ]
            )

            cleaned_items_output = response.choices[0].message.content
            st.markdown("### 🧾 Your Master Shopping Record")

            components.html(
                f"""
                <div style="max-height: 300px; overflow-y: auto; padding: 10px; border: 1px solid #ccc; border-radius: 8px;">
                    <pre style="white-space: pre-wrap;">{cleaned_items_output}</pre>
                </div>
                """,
                height=350,
                scrolling=True
            )
            

            # --- Extract Raw Items Only (for LLM use) ---
            store_blocks = extract_all_store_blocks(cleaned_items_output)
    
            combined_raw_items = "\n\n".join(
                f"**Store: {store}**\n{items}" for store, items in store_blocks
            )
    
            save_json({"store_blocks": store_blocks}, "master_shop_record.json")


        except Exception as e:
            st.error("There was a problem generating the shopping record.")
            st.exception(e)

    try:
        st.subheader("🩺 Household Behavior Profile")

        # --- Step 3: Generate Role-Based RDN Summary ---

        if user_role == "provider":
            pen_portrait_prompt = f"""
        You are an experienced and analytical Registered Dietitian Nutritionist (RDN) working in an endocrinology or primary care setting. You are reviewing a grocery receipt converted into a structured list of items (each with a raw name and, when available, a confident expansion). Your goal is to produce a detailed clinical assessment of the household’s dietary patterns to support patient education, behavior-change planning, and glycemic management.
        
        Step 1: Input Guidance
        Review the raw and expanded item names. Favor the expansion when available, but do not speculate beyond what is visible. Skip items marked “ambiguous.” Do not use any external food database — your assessment must be grounded entirely in the data provided.
        
        Step 2: Identify and Analyze Dietary Patterns  
        Use commonsense knowledge to infer the following, citing specific examples wherever possible:
        
        Carbohydrate Analysis:
        - Identify simple vs. complex carbohydrate sources.
        - Flag high-sugar items (e.g., sweetened beverages, desserts).
        - Note fiber sources (e.g., whole grains, legumes, produce).
        
        Protein and Fat Analysis:
        - Identify lean vs. high-fat protein sources.
        - Distinguish processed vs. whole protein items.
        - Flag saturated or trans fat sources (e.g., processed meats, baked goods).
        - Note any unsaturated fat sources (e.g., fish, nuts, oils).
        
        Sodium & Processed Food Intake:
        - Flag potential high-sodium foods (e.g., deli meats, frozen meals, canned items).
        - Categorize items as processed, minimally processed, or whole foods based solely on name and expansion. Use commonsense reasoning — do not fabricate or assume.
        
        Potential Nutrient Deficiencies or Excesses:
        - Identify any notable nutrient gaps (e.g., low produce variety, low fiber).
        - Flag excess intake risks (e.g., high sugar, high saturated fat).
        
        Meal Planning and Lifestyle Indicators:
        - Based on item combinations, infer likely meal prep habits (e.g., batch cooking, ready-to-eat reliance).
        - Identify budget-conscious choices (e.g., store brands, bulk buys).
        - Note any cultural or lifestyle indicators (e.g., flavor trends, busy schedules).
        - Infer household size/composition, if possible (e.g., presence of children, multiple dietary needs).
        
        Step 3: Write the Clinical Assessment Summary  
        Write a concise, critical summary of the observed dietary patterns, risks, and strengths. This analysis is for internal clinical use and will not be seen by the patient. Your tone should be:
        - Honest and evidence-based — do not sugarcoat or soften key concerns
        - Respectful and constructive — do not shame the household
        - Actionable — highlight areas for focused teaching and follow-up
        
        Emphasize aspects relevant to glycemic control, metabolic health, or other nutrition-related concerns. Avoid vague praise or overgeneralizations.
        
        Master Shop Record:
        {cleaned_items_output}
            """
            system_message = "You are a clinical RDN. Base your assessment primarily on Raw Item names, using Expansion only when it increases clarity and is not marked Ambiguous."
        
        elif user_role == "patient":
            pen_portrait_prompt = f"""
        You are a registered dietitian who specializes in empowering households to understand and improve their food choices. You are reviewing the output of a tool that converts a grocery receipt into a structured list of items. Each item may include a short name and, when possible, a longer expansion. You are creating a patient-facing summary to help the user understand their shopping habits and identify opportunities for improvement. The tone should be supportive but not overly positive — focus on clear, specific insights rooted in evidence and behavioral observation.
        
        Step 1: Review Input Format
        You are provided with a list of grocery items purchased by a household. Each row contains a raw item name and, when available, a confident expansion. Use both fields when identifying trends, favoring the expansion when it offers more clarity. Do not make assumptions based on items that are unclear or ambiguous.
        
        Step 2: Identify and Analyze Shopping Patterns
        Analyze shopping patterns based solely on the visible item names and expansions. Do not rely on any internal food database. Instead, use commonsense knowledge and observable trends. Where appropriate, cite examples from the list. Analyze for the following:
        
        - ✅ Recurring food categories, such as proteins, grains, snacks, dairy, beverages, sweets, condiments, or frozen meals. Name the categories only if there are multiple examples.
        - ✅ Household size & composition, if inferable (e.g., kids, adults, multiple dietary needs).
        - ✅ Meal preparation habits, such as reliance on convenience items vs. ingredients for home-cooked meals.
        - ✅ Spending habits, such as bulk items, store brands, or premium brands.
        - ✅ Dietary preferences or restrictions, such as gluten-free, low-carb, vegetarian, etc.
        - ✅ Brand preferences, if certain brands appear multiple times.
        - ✅ Lifestyle indicators, such as a busy or social household — include only if confident based on 3+ distinct items (≥60% confidence).
        - ✅ Unexpected or culturally specific patterns, like repeated purchases of a specific spice, dish, or ingredient type.
        
        Cite only patterns that are clearly supported by the data. Avoid vague or overly positive generalizations.
        
        Step 3: Write the Patient Summary
        Write a short, specific summary that reflects this household’s current shopping patterns. Use an empathetic tone, but prioritize clarity, usefulness, and behavioral insight. If relevant, comment on strengths and possible areas for improvement in a way that helps the household feel understood and supported. Do not mention any item that wasn’t clearly extracted or expanded.
        
        Master Shop Record:
        {cleaned_items_output}
            """
            system_message = "You are a registered dietitian. Base your summary on Raw Item names, using Expansion only when it improves clarity. Do not use expansions marked Ambiguous."
        
        else:
            pen_portrait_prompt = "Unknown user role."
            system_message = ""

        pen_portrait_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": pen_portrait_prompt}
            ]
        )

        pen_portrait_output = pen_portrait_response.choices[0].message.content

              # Final Output
       
  
        st.subheader("💡 Summary of Your Shopping Habits" if user_role == "patient" else "🩺 Final Household Summary")
        st.markdown(pen_portrait_output)
        with open(os.path.join(SESSION_FOLDER, "narrative_summary.txt"), "w") as f:
        f.write(pen_portrait_output)



    except Exception as e:
        st.error("There was a problem generating the Household Profile.")
        st.exception(e)

        
