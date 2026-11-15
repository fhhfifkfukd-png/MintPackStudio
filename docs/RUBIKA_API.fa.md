# قرارداد API روبیکا در MintPack Studio

## مبدأ و مسیر

تمام درخواست‌ها فقط به مبدأ HTTPS ثابت زیر ارسال می‌شوند:

`https://botapi.rubika.ir/v3/{token}/{method}`

بدنه درخواست JSON و متد HTTP از نوع POST است. میزبان و scheme از ورودی JavaScript قابل تغییر نیستند.

## getUpdates

بر اساس صفحه جزئیات رسمی متد:

- ورودی cursor: `offset_id` (اختیاری)
- ورودی تعداد: `limit` (اختیاری)
- خروجی: `updates` و `next_offset_id`

چرخه سرویس به این صورت است: مقدار cursor موجود را در `offset_id` ارسال می‌کند، updateها را در صف رمز/ذخیره محلی (بدون ذخیره متن خام token) قرار می‌دهد و سپس `next_offset_id` برگشتی را ذخیره می‌کند. cursor فقط پس از ثبت صف updateها جلو می‌رود.

> صفحه معرفی API از `start_id` نیز نام می‌برد؛ در کد این پروژه، برای متد `getUpdates` از schema صفحه جزئیات متد (`offset_id` / `next_offset_id`) استفاده شده است. اگر روبیکا قرارداد را تغییر دهد، قبل از ارتقای نسخه این فایل و تست قرارداد را با مستندات رسمی روز تطبیق دهید.

## نمونه JavaScript

```javascript
const result = await AppMint.rubikaRequest({
  token: "BOT_TOKEN",
  method: "getUpdates",
  payload: { offset_id: "CURSOR", limit: 100 }
});

// { httpStatus: 200, response: { ... official API JSON ... } }
```

## مراجع رسمی

- https://rubika.ir/botapi
- https://rubika.ir/botapi/methods
- https://rubika.ir/botapi/models
- https://rubika.ir/botapi/group-channel

این پروژه schema همه متدهای روبیکا را از نو تعریف نمی‌کند؛ `rubikaRequest` نام متد و payload را به API رسمی می‌فرستد و JSON پاسخ را به caller برمی‌گرداند.
