# Engineering_the_Trading_Edge.pdf — chiqarilish eslatması

Bu fayl repoda OCR natijasini tutish uchun. `Read`/IDE orqali PDF ko‘rilganda matn chiqmasa — bu sahifalar grafik/skanner ko‘rinishida bo‘lishi mumkin (ushbu nusxa 19 sahifa).

## Matn olish

Natijaviy **`engineering_the_trading_edge_native.txt`** repoda mavjud — faylda faqat yozuv yoʻqligi haqidagi izoh bor (PDF skan). Toʻliq matn uchun OCR qiling.

1. Kutubxonalar (bir marta):

   ```text
   pip install pymupdf pytesseract pillow
   ```

2. Tesseract bajarilishi `PATH`da bo‘lishi kerak (Windows: scoop/choco/winget yoki `.exe` qo‘lda).

3. Ishga tushirish:

   ```text
   cd us-stock-rvol-agents
   python scripts/extract_pdf_text.py "C:\Users\YOUR\Downloads\Engineering_the_Trading_Edge.pdf" -o docs/generated/engineering_the_trading_edge_extract.txt --ocr --dpi 200
   ```

4. Fayl yozilgach, tuzilmani xulosalash va strategiya parametrlari bilan tekshirish.

**Hozir:** OCR avtomatik bajarilgan nusxa bu repoda keltirilmagan (vosita va til paketlari foydalanuvchi mashinasiga bog‘liq). Yuqoridagi buyruq yordamidan foydalaning.
