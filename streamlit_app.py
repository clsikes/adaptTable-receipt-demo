import streamlit as st
from openai import OpenAI
import base64
import requests

# --- API Keys ---
GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
client = OpenAI(api_key=OPENAI_API_KEY)

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

query_params = st.experimental_get_query_params()
user_role = query_params.get("role", ["patient"])[0]  # default to patient

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
    st.session_state.uploaded_receipts.append(new_receipt)
    st.success("Receipt uploaded!")

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

    try:
        st.subheader("Generating Master Shopping Record...")


        system_prompt_receipt_parser = """
        You are an expert receipt parser. Your role is to extract and expand grocery items from OCR-processed receipts using consistent formatting and strict rules.
        Always:
        - Expand confidently known abbreviations using → 
        - Flag uncertain items under an 'Ambiguous Items' section
        - Preserve literal wording and ordering
        Do not guess, and do not skip expansions when confident.
        """

        user_prompt_receipt_parser = f"""
        SYSTEM PROMPT: Receipt Item Extraction & Formatting
        Task:
        Extract and format all items below from a grocery receipt processed through OCR (Optical Character Recognition) for inclusion in a master shopping record. This record will support later analysis of dietary habits, food preferences, and household size.
        Instructions:
        Data Review:
        • Review all extracted receipt content carefully.
        • Do not remove any items, including non-food or miscellaneous products.
        • Do not infer, hallucinate, or fabricate missing or unclear items.
        • Do not consolidate duplicates — list each item exactly as it appears and in the order it was found.
        Output Formatting:
        • Store Name: As printed on the receipt
        • Date: As printed on the receipt
        • Items:
        o Present as a numbered list, maintaining original order
        o For each item, preserve original wording.
        o Expand confidently known abbreviations or recognizable product names using → formatting, even if the original is abbreviated.
        o Always use → when expanding or correcting an item name.
        Abbreviation Expansion Rules:
        • Expand abbreviations or recognizable names only if you are highly confident of the full name (e.g., “GV Shpsh” → “Great Value Sharp Shredded Cheddar”), and always use → to show the expansion.
        • If you are not sure, leave the original abbreviation untouched and move the item to a clearly labeled “Ambiguous Items” section at the bottom, with a short note explaining why it wasn’t expanded.
        • If the exact item name is uncertain but the food category is confidently identifiable (e.g., fresh produce, dairy, snack foods), classify the item with a high-level category tag (e.g., “[Uncertain Product Name] – Fresh Produce”) instead of marking it ambiguous. Use this only when category assignment is useful for downstream dietary analysis and expansion would otherwise be speculative.
        OCR Correction Guidelines:
        • Correct only clear OCR typos (e.g., “Chedar” → “Cheddar”)
        • Do not interpret categories or food types — preserve the item’s literal content.
        • Prioritize data integrity over clarity. When unsure, keep the original.

        Example Output:
        
        Store Name: Walmart  
        Date: 03/21/2025  
        
        1. GV Shpsh → Great Value Sharp Shredded Cheddar  
        2. GV ZPR SANDW → Great Value Zipper Sandwich Bags  
        3. PAL ORI 828 → Palmolive Original 828ml  
        4. TIDEHEORG107 → Tide HE Original 107oz  
        5. CHRMNSF4 → Charmin Soft 4-pack  
        6. BNTYSAS2 4 → Bounty Paper Towels 2-ply 4-pack  
        7. NUTELLA 725G  
        8. 90G POUF → 90g Bath Pouf  
        
        Ambiguous Items:  
        1. CCSERVINGBWL – Unclear item code; not confidently identifiable

        Return only the structured output in this format. Do not add explanations, notes, or commentary.

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
        st.markdown("### 🧾 Master Shopping Record:")
        st.markdown(cleaned_items_output)

    except Exception as e:
        st.error("There was a problem generating the shopping record.")
        st.exception(e)

    try:
        st.subheader("🩺 Household Behavior Profile")


        # Step 1: Generate structured analysis (for provider view only)
        if user_role == "provider":
            structured_analysis_prompt = f"""
            You are a food classification and dietary behavior expert. Based on the Master Shop Record:
        
            1. Categorize all food items into standard groups (e.g., proteins, grains, produce, snacks).
            2. Identify notable shopping patterns (e.g., home cooking, cost-saving, brand use).
            3. Do not summarize or speculate.
        
            Return:
            ### Categorized Foods:
            (list by category)
        
            ### Observed Patterns:
            - Bullet 1
            - Bullet 2
        
            Master Shop Record:
            {cleaned_items_output}
            """
        
            structured_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a precise, unbiased food data analyst. Do not speculate."},
                    {"role": "user", "content": structured_analysis_prompt}
                ]
            )
            structured_analysis = structured_response.choices[0].message.content
        else:
            structured_analysis = ""  # no background analysis for patient view
        
        # Step 2: Generate patient-facing household profile summary
        pen_portrait_prompt = f"""
        You are a warm, evidence-based pediatric RDN focused on T1D. Write a household summary using the structured food analysis below. Be empathetic, non-judgmental, and avoid speculative lifestyle inferences unless 60%+ confidence is supported by item patterns.
        
        Format:
        ### Narrative Household Profile:
        (3–5 sentence summary)
        
        ### Notable Shopping Trends:
        - Bullet 1
        - Bullet 2
        - Bullet 3
        
        Structured Food Analysis:
        {structured_analysis if user_role == 'provider' else cleaned_items_output}
        """
        
        pen_portrait_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a thoughtful, supportive RDN. Base all insights on evidence from food patterns only."},
                {"role": "user", "content": pen_portrait_prompt}
            ]
        )
        pen_portrait_output = pen_portrait_response.choices[0].message.content
        if user_role == "provider":
            st.subheader("🩺 Full Clinical Profile")
            with st.expander("📊 Categorized Foods & Shopping Patterns", expanded=True):
                st.markdown(structured_analysis)
            st.markdown("#### Patient Summary View")
            st.markdown(pen_portrait_output)
        else:
            st.subheader("💡 Your Personalized Nutrition Snapshot")
            st.markdown(pen_portrait_output)


    except Exception as e:
        st.error("There was a problem generating the Household Profile.")
        st.exception(e)

        
