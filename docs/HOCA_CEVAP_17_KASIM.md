# Hocanın 17 Kasım cevabı: kararlar ve ne değişti

Kayıt tarihi: 22 Kasım 2026. Bu dosya hocanın cevabını ve onun üzerine alınan kararları kayda
geçirir. Hocaya cevap yazılmadı; yazar "şimdilik cevap yazmayalım" dedi. Plan: `docs/PLAN_ARALIK.md`.

## 1. Hocanın kararları

| Konu | Karar |
|---|---|
| Başlık ve kapsam | "RAG" başlıktan çıkar, filtresiz ANN araması. Onaylı |
| Kapsama geri alınanlar | Nedensel analiz (E19), `halfvec` ve `int8` (E20), PgBouncer (E21), minimal open-loop (E22), nDCG@10 (E23) |
| Future work | Filtreli ve hibrit arama, karma okuma-yazma, 16+ çekirdek, pgvectorscale/VectorChord, ikinci embedding modeli. 10M tek nokta: zaman kalırsa |
| Bellek deneyi | 1 Aralık ölçütü: tam sorgu seti, tekrar, bağımsız cold-start. Sağlanıyor; cgroup kısmı kalıyor |
| Dergi | Information Systems ilk hedef, sonra Journal of Systems and Software, PeerJ CS son. Gönderimden önce kapsam, makale türü, uzunluk sınırı kontrol edilecek |
| M6 | Her tablo için kullanılan `ef` noktası ve node/build metinde yazılacak |
| Tag | Makalede kullanılan harness commit'i bir tag ile sabitlenecek |
| Kesme sırası | Süre taşarsa önce open-loop, sonra 10M. Nedensel analiz ve quantization kesilmez |
| Takvim | 15 Aralık tam taslak, 22 Aralık'a kadar yorumlar, 8 Ocak 2027 gönderim |

## 2. Beş yeni taahhüt

| Taahhüt | Deney | Hedef | Kapı |
|---|---|---|---|
| Nedensel analiz: Qdrant farkı hangi mekanizmadan | E19 | G2 | Hiçbir motor sorgu başına mesafe sayısı vermiyor; kök yetkisi ve eBPF yok. Yedek: pgvector blok sayısı ve kullanıcı alanı `perf` sayaçları, sınırlar yazılır |
| `halfvec` ve `int8` quantization | E20 | G3 | Recall, gecikme, CPU, indeks boyutu aynı eşleşmiş recall noktasında |
| PgBouncer | E21 | G4 | Bağlantı havuzu ile ve havuzsuz, aynı `ef` |
| Minimal open-loop | E22 | G5 | Kesme sırasında ilk sırada |
| nDCG@10 | E23 | G6 | Qrels kapsamına bağlı (bölüm 3) |

## 3. Düzeltme notu: "qrels elimizde"

Hocaya gönderilen ilk mailde "Qrels elimizde olduğu için nDCG@10 de eklenebilir" yazıyor. Bu ifade
referee raporundan alınmıştı ve **doğrulanmadı**. Depoda ve artifacts dizininde qrels dosyası yok.
Ek olarak:

- `prepare_data` pasaj kimliklerini kaydetmemiş; kimlik eşlemesi için ilk 1M pasaj yeniden
  akıtılmalı.
- ANN koşuları dönen kimlikleri saklamıyor; nDCG için harness'a eklenecek (G1).
- İlk 1M pasaj, yargılı ilgili pasajların küçük bir kısmını kapsayabilir. Bu bir tahmindir, ölçülmedi.
- TREC DL 2021 ve 2022 qrels dosyaları herkese açık. 2023 dosyasının adı doğrulanmadı. Hiçbir şey indirilmedi.

Sonuç: nDCG@10 yapılabilir, ama kapsam ölçülmeden söz verilemez. G6'daki kapı kuralı: qrels
kapsamı yetersizse nDCG mutlak sonuç olarak sunulmaz, yalnızca limitasyon olarak yazılır. Bir sonraki
mailde bu düzeltme hocaya kısaca bildirilmeli (yazar karar verecek).

## 4. Belirsiz noktalarda alınan kararlar

Hocaya sorulmadı. En güçlü aday seçildi (ayrıntı `docs/PLAN_ARALIK.md` bölüm 2): nedensel analiz
en yüksek öncelik; tablolar tag'li kodun analiz araçlarıyla ham sonuçlardan üretilir ve her ham
sonuç kendi commit'ini manifestinde taşır; NVMe yeniden koşulmaz, sonuçlar "HDD" etiketiyle kalır;
nDCG için kapı kuralı; G2–G6 kod değişiklikleri tek pakette (G1).

## 5. `docs/MAIL_HOCA_DURUM_2.md` durumu

Taslağın 1–3. maddeleri (kapsam, dergi, son tarih) cevaplandı ve eskidi. Gönderilmeyecek; yazar
cevap kararı verdiğinde yeni taslak bu dosyadan yazılır.

## 6. M6 kaynak ifadesi

Makalede `tab:sources` her tablo ve şekil için build sayısını, job ve node'ları ve `ef` noktasını
verir. E1'de iki motor farklı node'larda kuruldu ve ölçüldü; bu metinde yazılıdır. E6'da `ef`,
0,95'e ulaşan en küçük taranmış değerdir (interpolasyon değil), bu yüzden iki motorun recall'u
0,951–0,957 arasında ve aynı değil.
