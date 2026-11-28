# Aralık planı, ikinci bölüm: depolama bulgusundan sonra (28 Kasım 2026'da yazıldı)

`docs/PLAN_ARALIK.md` G0–G10 bitti. Bu belge kalan işleri ve yeni hedefleri (G11–G16) tanımlar. Genel kurallar
(`PLAN_ARALIK.md` bölüm 3) aynen geçerli: önce test, smoke → pilot → tam kapıları, her sayı kaynak dosyadan,
**onay olmadan dışarıya hiçbir şey gönderilmez**, SSH koptuğunda önce kuyruğa bakılır.

## 1. Neyin değiştiği

28 Kasım'da hocanın "TRUBA'da NVMe kullanabilirsin, /tmp de" cümlesini sınadık. Eylül'deki "kümede NVMe yok" sonucu tek bir hamsi düğümüne dayanıyordu.

| Düğüm | Bölüm | `/tmp` | NVMe |
|---|---|---|---|
| hamsi120, hamsi124 | hamsi | dönen disk, ext4 | yok |
| orkinos1 | smp | dönen disk, ext4 | yok |
| barbun16 | barbun | dönen disk (PERC H730P), ext4 | yok |
| akya7 | akya-cuda | SATA SSD | yok |
| **orfoz183** | **orfoz** | **NVMe (Micron 7450, 894 GB), `/` ile aynı** | **var** |

TRUBA dokümanı (24 Aralık 2025 tarihli) "tüm sunucularda /tmp NVMe" diyor; ölçümlerimiz bunu orfoz için doğruluyor, hamsi, barbun, smp ve akya7 için
doğrulamıyor. NVMe yalnızca orfoz'da bulundu ve orfoz'un işlemcisi hamsi'den farklı (112 çekirdek). Sonuç: orfoz'daki sonuçlar hamsi sonuçlarıyla aynı tabloda
karşılaştırılamaz, **ayrı bir platform ve ayrı bir tam set** olarak raporlanır. Tek bir kolu başka platformda koşmak karşılaştırmayı bozar, yapılmaz.

## 2. Kararlar (itiraz edebilirsiniz)

1. **İki ayrı tam set.** Set 1: hamsi/HDD (mevcut E10 + eksik pgvector 4G kolları). Set 2: orfoz/NVMe (E10'un tamamı). Her set kendi içinde tutarlı.
2. **"4G tamamlanamadı" yetmez.** 3 saatlik sınırı biz koyduk, kuyruk sınırı 3 gün. 4G kolları uzun limitle yeniden koşulur; bitmezse "3 günlük sınırda da bitmedi" yazılır.
3. **Önce maliyet, sonra iş.** G12 salt okunur bir hesap; G13 ve G14 ona göre boyutlanır. Sığmazsa kesme sırası: önce orfoz setini küçült, sonra gerekçeli olarak "HDD, en kötü durum" sınırına dön (hocanın kendi yedek yolu).
4. **Hocanın mailinde TRUBA hesabından bahsedilmez.**

## 3. Hedefler

### G11. Depolama kanıtının kapanışı (28–29 Kasım)

**Yapılacaklar:** Barbun, orfoz, akya7 sonuçlarını `docs/STORAGE_CHECK.md` ve `docs/NE_DEGISTI.md` içine işle. Makaledeki üç cümleyi (Environment, Threats/Storage, Future work),
`paper/referee_response.md` M4 ve `docs/E10_MEMORY_DECISION.md`, `docs/ACIK_MADDELER.md`, `docs/MAIL_HOCA_TESLIM.md` içindeki NVMe ifadelerini bu tabloya göre eşitle. Hocaya yazılacak mail taslağını
(yazışma dosyasına göre: "Ekim'de HDD yazmıştım, siz NVMe dediniz, baktım") `docs/MAIL_HOCA_TESLIM.md` içine yerleştir.

**Bitti sayılması için:** tablo 7 düğümü de içeriyor, `grep -rn "NVMe" paper docs` içindeki hiçbir cümle "kümede NVMe yok" ya da "tek düğüm" demiyor, testler geçiyor, push edildi.

### G12. E10 maliyet ve takvim hesabı (29–30 Kasım, salt okunur)

**Yapılacaklar:** `data-manifests/e10_full_0b0b905.json` ve çıktılarından E10'un iş sayısını, işin süresini, pgvector 4G için gerçekçi süreyi (8 GB soğuk başlangıç, sorgu başına süre) ve orfoz kuyruğu için `sbatch --test-only` tahminini çıkar.
Orfoz için pinning'i (`bench/env.sh`, `bench/slurm/*`, 2 soket × 56 çekirdek) ve whole-node kuralını yaz. Hamsi 4G tekrarı ve orfoz seti için tahmini bitiş tarihlerini ver.

**Bitti sayılması için:** `docs/E10_NVME_PLAN.md`: tüm rakamlar manifestten ya da `sbatch --test-only`'dan, tahminler tahmin diye etiketli, 15 Aralık'a sığma sonucu ve kesme önerisi yazılı. **Hiçbir iş gönderilmez.**
Sonuç, 1 Aralık bellek kararı olarak `docs/E10_MEMORY_DECISION.md` içine eklenir.

### G13. Set 1 tamamlama: hamsi'de pgvector 4G kolları (1–12 Aralık)

**Yapılacaklar:** Aynı commit/config ile (`0b0b905`) 2 tampon ayarı × 3 tekrar = 6 iş, G12'de hesaplanan uzun limitle (kuyruk sınırı 3 gün). Smoke/pilot kapıları, katı denetim, ayrı manifest, analiz, makaledeki Memory Pressure bölümünde güncelleme.

**Bitti sayılması için:** ya 6 sonuç manifestte ve denetimden sıfır hatayla geçti, ya da koşular kuyruk sınırında bitmedi ve bu, manifestte ve makalede "3 günlük sınırda da bitmedi" olarak yazılı. Her iki durum da hedefi kapatır.

### G14. Set 2: orfoz/NVMe E10 seti (1–12 Aralık)

**Yapılacaklar:** G12'de kararlaştırılan kapsamla E10'un orfoz karşılığı: orfoz pinning uyarlaması, smoke → pilot → tam, aynı sorgu seti ve cgroup yöntemi, depolama kontrolü her işin kaydında (`lsblk`, `/tmp` kaynağı). Ayrı manifest ve analiz, platform farkı (işlemci, çekirdek, düğüm) tabloda açık.

**Bitti sayılması için:** G12'deki kapsamın tamamı sonuçlandı ya da kapsam azalması G12 belgesinde gerekçeli; makalede ayrı tablo/alt bölüm; "NVMe etkisi" ile "platform etkisi"nin ayrılamadığı sınırı yazılı.
**Yedek yol:** orfoz kuyruğu 12 Aralık'a kadar yetmezse yalnızca biten kısım raporlanır, kalan "HDD en kötü durum" sınırıyla bırakılır.

### G15. Makale ve doğrulama güncellemesi (9–14 Aralık)

**Yapılacaklar:** G13/G14 sonuçlarını makaleye yaz; `docs/PAPER_VERIFY.json`, `PAPER_CLAIMS.json` ve tablo bağlarını yeni analizlerle genişlet; `make verify-paper` temiz; `analysis-v3` tag'ı; `paper/referee_response.md` (M4, M5) ve Threats bölümünü güncelle.

**Bitti sayılması için:** `make verify-paper` sıfır hata, tüm yeni tablolar bir manifeste bağlı, tag oluşturuldu ve push edildi. Derleme sizin işiniz (Overleaf).

### G16. Teslim paketi (15 Aralık)

**Yapılacaklar:** `docs/DELIVERY_CHECK.md` ve `docs/NE_DEGISTI.md`'yi yenile; son doğrulama turu; açık maddeler; hocaya gidecek mailin son hali (gönderme sizin).

**Bitti sayılması için:** testler ve `make verify-paper` temiz, depo temiz ve push'lu, mail taslağı güncel.

## 4. Sizin işleriniz

| Ne | Ne zamana kadar |
|---|---|
| Hocaya mail (taslak G11'de) | Siz uygun görünce; G12 sonucu bekleniyorsa 1 Aralık |
| G13/G14 için `/goal` ile onay | G12'den sonra |
| Overleaf'te derleme | 14 Aralık |
| AI beyanı, rekabet/finansman beyanları, CRediT, yazışma yazarı | 14 Aralık |
| Information Systems yazar kılavuzunu tarayıcıda okumak | 14 Aralık |

## 5. Riskler

- **Orfoz kuyruğu:** bölüm dolu; kontrol işleri bile saatlerce bekledi. Tam düğüm, 3 saate kadar işler çok daha uzun bekleyebilir. Önlem: G12'de ölçülen bekleme, kapsam küçültme yolu yazılı.
- **4G kolları NVMe'de de bitmeyebilir.** Bu da bir sonuçtur ve "bitmedi" diye raporlanır.
- **Platform karışıklığı:** orfoz'da NVMe etkisi ile CPU etkisi ayrılamaz; sınır makalede yazılı.
- **Tek kişi, 8 Ocak gönderim:** takvim 15 Aralık taslağına bağlı; G14 kesilebilir, G13 ve G15 kesilmez.
- **Yazışma dosyasında TRUBA şifresi açık duruyor** (23 Eylül maili); dosya depoya, Drive'a ya da başka bir yere konmamalı.
