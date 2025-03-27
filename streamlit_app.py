# --- If User Chooses to Proceed ---
if proceed:

    # --- ChatGPT Prompt: Item Extraction & Formatting ---
    st.subheader("Generating Master Shopping Record...")

    prompt = f"""
    SYSTEM PROMPT: Receipt Item Extraction & Formatting  
    Task:  
    Extract and format all items from a grocery receipt processed through OCR (Optical Character Recognition) for inclusion in a master shopping record. This record will support later analysis of dietary habits, food preferences, and household size.

    Instructions:
    1. Data Review:
    - Review all extracted receipt content carefully.  
    - Do not remove any items, including non-food or miscellaneous products.  
    - Do not infer, hallucinate, or fabricate missing or unclear items.  
    - Do not consolidate duplicates — list each item exactly as it appears and in the order it was found.

    2. Output Formatting:
    - Store Name: As printed on the receipt  
    - Date: As printed on the receipt  
    - Items:
      - Present as a numbered list, maintaining original order  
      - For each item, preserve original wording.  
      - Only add an expanded version when the abbreviation is clearly and confidently known.

    3. Abbreviation Expansion Rules:
    - Expand abbreviations only if you are highly confident of the full name (e.g., “GV Shpsh” → “Great Value Sharp Shredded Cheddar”).  
    - If you are not sure, leave the original abbreviation untouched.  
    - Use → to show expansions or corrections (e.g., GV Shpsh → Great Value Sharp Shredded Cheddar).

    4. OCR Correction Guidelines:
    - Correct only clear OCR typos (e.g., “Chedar” → “Cheddar”)  
    - Do not interpret categories or food types — preserve the item’s literal content.  
    - Prioritize data integrity over clarity. When unsure, keep the original.

    Return only the structured output in this format. Do not add explanations, notes, or commentary.

    Extracted Receipt Text:
    {text}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        cleaned_items_output = response.choices[0].message.content
        st.markdown("### 🧾 Master Shopping Record:")
        st.markdown(cleaned_items_output)

    except Exception as e:
        st.error("There was a problem extracting text or generating the shopping record.")
        st.exception(e)
