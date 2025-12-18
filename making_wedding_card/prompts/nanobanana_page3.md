**Page 3 - Venue Information (Map Overlay):**

**[Input Requirements]**
- Context Reference: The generated image from Page 2
- Map Asset: Provided map image
- Style Reference: Provided style reference image

**[Execution Prompt]**
Create the third page as a flat, print-ready digital design.
1.  **Layer 1 - Background (Priority):** First, fill the canvas with the **identical background texture and {border_design_id}** from Page 2. The visual context MUST remain 100% consistent with the previous pages before adding content.
2.  **Layer 2 - Map Integration:** Place the provided map image in the upper or center area.
    * **Do not stylize or recolor the map.** Use the original map image.
    * **Scale:** **Resize the map smaller** so it fits comfortably INSIDE the border margins. It must NOT touch the edges or cover the frame. Ensure the page background is visible around the map.
3.  **Layer 3 - Text:** Below the map, add the venue details: {venue}, {venue_address}, {wedding_date} {wedding_time}, and {texts[location]}.
4.  **Text Styling:** strictly apply the **same font style and text color** used in Page 2. **Do not use default black.**