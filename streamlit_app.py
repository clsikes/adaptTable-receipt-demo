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
            You are an expert receipt parser. Your role is to extract and expand grocery items from OCR-processed receipts using consistent formatting and strict rules.

            Return the output as a markdown table with two columns:
            | Raw Item | Expansion |
            List every item in order. Include the raw name as-is.
            Expand confidently known abbreviations using the Expansion column.
            If unsure, leave Expansion blank or mark as 'Ambiguous'.

            Do not consolidate duplicates or make guesses.
            Do not remove non-food items.
            Preserve order and literal wording in the Raw Item column.
            """

            user_prompt_receipt_parser = f"""
            Extract and expand grocery items from the following OCR receipt text.
            Follow the formatting rules below.

            ### Format:
            | Raw Item | Expansion |
            |----------|-----------|
            | GV SHPSH | Great Value Sharp Shredded Cheddar |
            | FLKY BISCUIT | Flaky Biscuits |
            | CCSERVINGBWL | Ambiguous |
            
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

            # --- Extract Raw Items Only (for LLM use) ---
            import re
            def extract_raw_items(markdown_table):
                rows = markdown_table.strip().split("\n")
                raw_items = []
                for row in rows:
                    if row.startswith("|") and not row.startswith("| Raw Item"):
                        parts = row.split("|")
                        if len(parts) > 1:
                            raw = parts[1].strip()
                            if raw and raw.lower() != "raw item":
                                raw_items.append(raw)
                return "\n".join(raw_items)

            raw_items_only = extract_raw_items(cleaned_items_output)

            if user_role == "provider":
                st.markdown("### 🧾 Master Shopping Record (Raw + Expanded):")
                st.markdown(cleaned_items_output)



        except Exception as e:
            st.error("There was a problem generating the shopping record.")
            st.exception(e)

    try:
        st.subheader("🩺 Household Behavior Profile")

        # --- Step 3: Generate Role-Based RDN Summary ---
        if user_role == "provider":
            pen_portrait_prompt = f"""
        You are an analytical and evidence-based Registered Dietitian Nutritionist (RDN) working in an endocrinology clinic. You have just received a Master Shop Record containing a list of raw grocery receipt items, with optional expanded names.

        Your job is to create a clear, structured evaluation of this household's dietary habits. This is for internal use only and will inform how to tailor patient education and support — it will not be seen by the patient. Be precise and direct. Do not speculate or assign blame.

        Instructions:
        - Base your assessment ONLY on the Raw Item names in the Master Shop Record. Ignore the expansion column.
        - Focus on dietary patterns, macronutrient quality, and clinical implications for diabetes or glycemic control.
        - Do not categorize items or infer food groups — instead, infer patterns based on known food items.
        - Avoid overgeneralizing from isolated purchases.

        Your output should include:

        ### Clinical Assessment Summary:
        (A brief, direct analysis of food behaviors and clinical considerations)

        ### Key Dietary Insights:
        - Bullet 1
        - Bullet 2
        - Bullet 3

        Master Shop Record:
        {raw_items_only}
            """
            system_message = "You are a clinical RDN. Use only the Raw Item names. Base all insights strictly on evidence from the item names alone."

        else:
            pen_portrait_prompt = f"""
        You are an empathetic, evidence-based Registered Dietitian Nutritionist (RDN) specializing in Diabetes. You’ve just received a Master Shop Record of grocery items — it includes a column of raw item names and optional expanded names.

        Your job is to write a short, clear narrative summary that describes this household's grocery habits and food patterns. This summary will be seen by the patient, so it should be easy to understand and reflect their shopping patterns accurately.

        Objective: Build trust and show that the user's food choices are understood, before providing any behavior change guidance.

        Instructions:
        - Base your summary entirely on the Raw Item names in the Master Shop Record. Ignore the expansion column.
        - Focus on consistent patterns, not isolated items.
        - Avoid making dietary category guesses unless strongly supported.
        - Keep the tone clear, observational, and specific — not vague or overly flattering.

        Output should include:

        ### Narrative Household Profile:
        (3–5 sentence descriptive summary that reflects the household and food patterns)

        ### Notable Shopping Trends:
        - Bullet 1
        - Bullet 2
        - Bullet 3

        Master Shop Record:
        {raw_items_only}
            """
            system_message = "You are an empathetic RDN. Base all insights only on the Raw Item names. Avoid guessing or using expanded names."

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



    except Exception as e:
        st.error("There was a problem generating the Household Profile.")
        st.exception(e)

        
