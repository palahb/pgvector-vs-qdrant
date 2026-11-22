# Aralık planı: hocanın 17 Kasım cevabına göre (22 Kasım 2026'da yazıldı)

Bu plan `/goal` komutlarıyla çalışmak için yazıldı. Her hedefin "Bitti sayılması için" bölümü
yalnızca benim üretebileceğim, transkriptte ve depoda doğrulanabilir kanıtlardan oluşur
(manifest, sıfır hatalı denetim, test, push). Hocanın ya da yazarların kararına bağlı şeyler hedefin
dışında tutuldu; engel çıkarsa hedefin **yedek yolu** önceden yazılı ve o yolun belgelenmesi hedefi
kapatır.

## 1. Hocanın cevabı ne değiştiriyor

| Konu | Karar |
|---|---|
| Başlık ve kapsam | "RAG" başlıktan çıkar, filtresiz ANN araması. Onaylı |
| Geri çağrılan (artık kapsam içi) | Nedensel analiz, `halfvec` + `int8`, PgBouncer, minimal open-loop, nDCG@10 |
| Future work | Filtreli ve hibrit arama, karma okuma-yazma, 16+ çekirdek, pgvectorscale/VectorChord, ikinci embedding modeli. 10M tek nokta: zaman kalırsa |
| Bellek deneyi | 1 Aralık ölçütü: tam sorgu seti, tekrar, bağımsız cold-start. **Sağlanıyor**, cgroup kısmı kalır |
| Dergi | Information Systems ilk hedef, sonra Journal of Systems and Software, PeerJ CS son. Gönderimden önce kapsam, makale türü, uzunluk sınırı kontrol edilecek |
| M6 | Her tablo için hangi `ef` noktası ve hangi node/build kullanıldığı metinde yazılacak |
| Tag | Makalede kullanılan harness commit'i bir tag ile sabitlenecek |
| Kesme sırası | Süre taşarsa önce open-loop, sonra 10M. Nedensel analiz ve quantization kesilmez |
| Takvim | 15 Aralık tam taslak ona, 22 Aralık'a kadar yorumları, **8 Ocak 2027 gönderim** |

## 2. Belirsiz noktalarda aldığım kararlar (itiraz edebilirsiniz)

1. **Nedensel analiz en yüksek öncelik.** Mailde "sondan ikinci sıraya" yazıyor ama geri kalanı onu
   vazgeçilmez sayıyor.
2. **Tag politikası:** Makale tablo ve şekilleri, tag'lenen kodun analiz araçlarıyla ham sonuçlardan
   üretilir. Her ham sonuç, onu üreten commit'i manifestinde taşımaya devam eder ve makale bunu
   yazar. Her şeyi tek commit'le yeniden koşmak günler alır ve sonucu değiştirmez.
3. **NVMe:** Bellek deneyi yeniden koşulmaz, sonuçlar "HDD" etiketiyle kalır. NVMe'nin hangi
   bölümde olduğu yalnızca kontrol edilir (G7), zaman kalırsa tek yapılandırma denenir.
4. **nDCG kapı kuralı:** Qrels kapsamı yetersizse nDCG mutlak sonuç olarak sunulmaz (G6).
5. **Tek harness commit'i:** G2–G6'nın kod değişikliklerini tek pakette (G1) yazıp tek smoke ile
   açarım. Kapı (smoke → pilot → tam koşu) commit başınadır ve bu bana günler kazandırır.

## 3. Genel kurallar (her hedef için)

- Önce test, sonra kod. Yeni deney smoke → pilot → tam koşu kapılarından geçer (`ORCHESTRATION.md`).
- Her tam koşu: katı denetim sıfır hata ve sıfır uyarı, manifest, analiz JSON'u, özet, commit, push.
- Sayılar makaleye yazılmadan önce analiz dosyasından yeniden hesaplanır.
- Dışarıya hiçbir şey gönderilmez (mail, issue, gönderim) onayınız olmadan.
- SSH koptuğunda boş çıktı "olmadı" demek değildir; yeniden denemeden önce kuyruğa/kayda bakılır.
- Kuyruk önceliğimiz düşük. Tam koşular 1,5 saatlik limitle gönderilir (arkadan doldurmaya girer).
- Bir hedefin bitişi **sonucun olumlu çıkmasına bağlı değildir**: olumsuz ya da kısmi sonuç, doğru
  yazılırsa hedefi kapatır.

## 4. Hedefler

Sıra önerisi: G0 → G1 → (G2, G3, G4, G5, G6 paralel yürür ama hedefler tek tek verilir) → G7 → G8 →
G9 → G10.

### G0. Zemin işleri (22–23 Kasım)

**Yapılacaklar**
- Hocanın cevabını ve kararlarını `docs/` altında kayda geçir (yukarıdaki tablo).
- İddia envanteri ve referee yanıtına yeni taahhütleri (beş madde) işle.
- M6 metni: makaledeki her tablonun hangi `ef` noktasını, hangi node/build'i kullandığını yaz.
  E1/E2 tablolarında bu bilgi baseline'dan çıkarılır (job ve node baseline manifestinde var).
- Hocaya gönderilen mailde doğrulanmamış bir taahhüt (qrels "elimizde") bulundu; düzeltme notu
  `docs/` altına yazılır.

**Bitti sayılması için**
- `docs/HOCA_CEVAP_17_KASIM.md` yazıldı. `docs/CLAIM_INVENTORY.md` ve `paper/referee_response.md`
  güncellendi.
- Makalede M6 için tablo başına `ef`/node/build ifadesi var; yapısal kontrol (ortam, etiket, atıf)
  temiz; 100+ test geçiyor; commit push edildi.

**Yedek / engel:** yok.

### G1. Tek harness paketi (23 Kasım–1 Aralık)

**Yapılacaklar** (hepsi test-first, tek commit zinciri, tek smoke)
- ANN koşuları döndürülen satır numaralarını da kaydeder (nDCG için; şu an yalnızca "kaç komşu").
- `perf record` kancası (isteğe bağlı bayrak): sunucu işlemlerinin kullanıcı alanı örneklemesi.
- pgvector `halfvec` seçeneği (sütun `halfvec(1024)`, `halfvec_cosine_ops`).
- Qdrant `int8` scalar quantization seçeneği (`always_ram`, `rescore` ayarı kaydedilir).
- Open-loop yük üreteci (Poisson varış, gecikme planlanan gönderim zamanından ölçülür).
- PgBouncer kancası (G4'ün fizibilitesine bağlı, yoksa atlanır).

**Bitti sayılması için**
- Her özellik için birim test yazıldı ve geçiyor (varsayılanlar eski davranışı birebir koruyor).
- Temiz ağaçta tüm testler geçiyor, commit push edildi, o commit için smoke `COMPLETED 0:0`,
  katı denetim temiz, kapı TRUBA kaydına işlendi.

**Yedek:** Bir özellik tek başına sorun çıkarırsa paketten çıkarılır, diğerleri ilerler ve çıkarılan
özelliğin hedefi yedek yoluna geçer.

### G2. Nedensel analiz, E19 (24 Kasım–2 Aralık)  *en önemli hedef*

**Soru:** Qdrant'ın ve pgvector'ün sorgu başına CPU'su nereye gidiyor?

**Yapılacaklar**
- Sembol fizibilitesi: Apptainer imajındaki `postgres` ve `qdrant` ikililerinde `perf record` ile
  fonksiyon adı çözülüyor mu? Debian paketlerinde iç fonksiyon sembolleri ayrı bir pakette olabilir,
  bu bir risk, kontrol edilecek.
- pgvector için: sorgu başına blok erişimi (kayıtlı) ve CPU ile elemanı başına maliyet; buffer manager
  payı (semboller varsa `perf` profili).
- Her iki motor için: sorgu başına talimat ve cycle (kayıtlı sayaçlardan), mesafe çekirdeğinin
  (`E7`, 1024 boyut: 1.504 / 282 / 248 ns) kullanılarak "mesafe işi payı" tahmini.
- Mesafe sayısı doğrudan ölçülemiyorsa (root yetkisi yok, eBPF yok) vekil ve sınır açıkça yazılır.
- Makaleye "Causal decomposition" alt bölümü; M11 yanıtı güncellenir.

**Bitti sayılması için**
- Smoke → pilot → tam koşu manifestleri, katı denetim sıfır hata.
- Analiz JSON'u ve özeti commit'li; makalede alt bölüm var; her sayı analiz dosyasından yeniden
  hesaplandı; iddia envanteri güncel; push edildi.
- Ölçülemeyen büyüklükler makalede "tahmin" ya da "ölçülmedi" diye işaretli.

**Yedek:** Semboller çözülmezse analiz yalnızca sayaçlarla yapılır (sorgu başına talimat, cycle,
IPC, blok erişimi, çekirdek karşılaştırması); sınır makaleye yazılır. Hedef yine kapanır.

### G3. Quantization, E20 (24 Kasım–4 Aralık)

**Soru:** "pgvector iki kat yer kaplıyor" bulgusu `halfvec` ile ne oluyor? Qdrant `int8` ile ne kazanıyor?

**Yapılacaklar:** 1M, her yapılandırma 3 build: pgvector `vector` ve `halfvec`, Qdrant float32 ve `int8`.
İndeks/depolama boyutu, build süresi, eşleşmiş recall'da gecikme ve CPU, recall kaybı (float32 yer
doğruluğuna karşı), sorgu başına recall dağılımı.

**Bitti sayılması için**
- Manifest, denetim, analiz, makalede alt bölüm (boyut ve hız tablosu), "iki kat" iddiasının
  yeni hâli yazıldı ve doğrulandı.

**Yedek:** `halfvec` HNSW indeksi 1024 boyutta beklenmedik biçimde çalışmazsa bu belgelenir, Qdrant
tarafı yine raporlanır.

### G4. PgBouncer, E21 (25 Kasım–4 Aralık)

**Soru:** Tartışmadaki "bağlantı havuzu kullanın" önerisi doğru mu?

**Yapılacaklar:** Önce fizibilite: PgBouncer'ı imaj olarak edinebiliyor muyuz (giriş düğümünde
internet var, bilinen imajlar var, ama digest sabitleme ve Apptainer'a çevirme gerekir)? Mümkünse
C=32 ve C=48'de havuz çekirdek sayısına eşit, pgvector doğrudan bağlantıyla karşılaştırması,
eşleşmiş recall, 3 tekrar.

**Bitti sayılması için** (ikisinden biri)
- (a) Ölçüldü: manifest, denetim, analiz, makale metni; **ya da**
- (b) İmaj edinilemedi/işlemedi, nedeni belgelendi ve Tartışma'daki öneri makaleden kaldırıldı
  (hocanın yazdığı yedek: "ya ölçelim ya öneriyi kaldıralım").

### G5. Minimal open-loop, E22 (26 Kasım–6 Aralık)  *kesilecek ilk madde*

**Yapılacaklar:** 1M, eşleşmiş recall, doygunluğa göre 3–4 sabit yük seviyesi (örneğin %50, %80,
%95, %110), Poisson varış, p99 ve p99.9, 3 tekrar, her iki motor.

**Bitti sayılması için**
- Üreteç testleri geçiyor (varış dağılımı, planlanan zamandan ölçüm), manifest, denetim, analiz,
  makalede alt bölüm. Kapalı döngü sonuçlarıyla farkı yazıldı.

**Yedek:** Süre taşarsa hocanın kuralıyla ilk bu kesilir. Bu durumda hedef, kesildiğinin ve
nedeninin `docs/` altında kaydıyla kapanır ve makaleye "open-loop ölçülmedi" sınırı yazılır.

### G6. nDCG@10, E23 (kapılı, 23 Kasım–6 Aralık)

**Önkoşul (sizden onay):** TREC DL 2021–2023 qrels'ini (herkese açık) indirmem ve ilk 1M pasajın
kimliklerini Hugging Face'ten yeniden çekmem. Yeni dosya adreslerinden 2021 ve 2022 var, 2023'ün
adı doğrulanamadı.

**Yapılacaklar**
1. Qrels'i edin, pasaj kimlikleri ile eşleştir (v2 belge kimlikleri ile v2.1 parça kimlikleri
   arasında belge düzeyinde eşleme gerekebilir).
2. **Kapı:** ilk 1M'de kaç sorgunun en az bir alakalı pasajı var, toplam alakalı pasajın yüzde kaçı
   korpusta? Eşik ve karar kuralı bu adımda, ölçümden önce yazılır.
3. Kapıyı geçerse: ANN koşularında döndürülen kimliklerden nDCG@10, MRR@10, Recall@10; kesin
   (kaba kuvvet) aramanın nDCG'si üst sınır; ANN recall'ı ile nDCG ilişkisi.

**Bitti sayılması için** (ikisinden biri)
- (a) Kapı geçti, nDCG ölçüldü, manifest, denetim, analiz, makale alt bölümü; **ya da**
- (b) Kapı geçmedi: ölçülen kapsam ve kararı `docs/` altına yazıldı, makalede nDCG "yalnızca duyarlılık
  analizi" ya da "ölçülmedi, kapsam yetersiz" diye dürüstçe geçiyor.

### G7. Bellek kararı ve depolama kontrolü (24 Kasım–1 Aralık)

**Yapılacaklar:** Hocanın 1 Aralık ölçütünü E10 sonuçlarıyla karşılaştırıp kararı kayda geç
(cgroup kısmı kalıyor). Bir hesaplama düğümünde `lsblk` ile NVMe/tmpfs bölümlerini ve `/tmp`'nin
gerçek diskini kontrol et. pgvector 4G kolları: varsayılan "tamamlanmadı" (karar sizde).

**Bitti sayılması için:** karar notu ve depolama kontrol çıktısı `docs/` altında. NVMe yoksa
makale "HDD en kötü durum" sınırını zaten taşıyor. Zaman kalırsa tek yapılandırmalı NVMe pilotu
stretch.

### G8. Titizlik ve tekrar üretilebilirlik (3–10 Aralık)

**Yapılacaklar**
- M7'nin kalanı: eşleşmiş recall'da throughput interpolasyonu.
- Motor derleme bayrakları ve komut seti bilgisini kaydet (m7).
- Tag politikası (bölüm 2): son harness commit'ine tag, tüm tablo/şekillerin tag'li analiz
  araçlarıyla ham sonuçlardan yeniden üretildiğini doğrulayan tek komut (`make verify-paper`).
- Commit/job/node tablosu: her deney için üreten commit.

**Bitti sayılması için:** tag oluşturuldu ve push edildi, `make verify-paper` temiz çalışıyor ve
çıktısı kayıtlı, makaledeki her tablo bir manifeste bağlanıyor.

### G9. Makale ve şablon (9–14 Aralık)

**Yapılacaklar**
- Yeni çerçeve ("vektör veritabanı benchmark'ları nasıl yanlış gider"), yeni alt bölümler (G2–G6),
  özet, giriş katkı listesi, sonuç, tehditler, gelecek çalışma listesi (hocanın future work listesi).
- Information Systems için: kapsam, makale türü, uzunluk sınırı, yapay zekâ beyanı yeri kontrolü
  (kaynaktan), sonra Elsevier şablonuna dönüştürme.
- Boyut bulgusu "tek modelin ön ek kesimi" olarak sınırlı kalır.

**Bitti sayılması için:** makale metni tamam, `\todo` yok, yapısal kontrol temiz, Elsevier sürümü
`paper/` altında, her sayı kaynak dosyasından doğrulandı, push edildi.
**Not:** Burada TeX yok. Derleme sizin Overleaf'te yapmanız gereken adımdır (bölüm 5).

### G10. Hocaya teslim paketi (15 Aralık)

**Bitti sayılması için:** son bir doğrulama turu (tüm testler, tüm manifestler, depo temiz ve
push'lu), bir "ne değişti" özeti, açık kalan maddeler listesi, hocaya gönderilecek metnin taslağı
(gönderme sizin).

## 5. Sizin işleriniz (hedeflerin dışında, tarihli)

| Ne | Ne zamana kadar |
|---|---|
| G6 için qrels indirme + kimlik çekme onayı | 24 Kasım |
| pgvector 4G kolları: raporla mı, uzun limitle mi koşalım? | 1 Aralık (varsayılan: raporla) |
| Overleaf'te derleme ve biçim kontrolü | 14 Aralık |
| AI kullanım beyanının okunup onaylanması | 14 Aralık |
| Hocaya cevap maili | Ne zaman isterseniz, taslağı ben yazarım |
| pgvector issue'sunun onayı | İsteğe bağlı, tekrar üretici betik henüz çalıştırılmadı |

## 6. Riskler

- **Kuyruk:** hesabımızın önceliği düşük, her kapı döngüsü saatler ya da günler sürebilir.
  Önlem: tek harness paketi, 1,5 saatlik limit, paralel pilot.
- **Semboller:** G2'nin derin kısmı bunlara bağlı, yedek yol yazılı.
- **PgBouncer imajı** edinilemeyebilir, yedek yol yazılı.
- **Qrels kapsamı** düşük çıkabilir, kapı kuralı yazılı.
- **Tek kişi, bir ay:** kesme sırası belli (G5, sonra 10M).
- **Port çakışması ve SSH kopmaları:** port beklemesi koda eklendi; kopmalarda kuyruğa bakılır.
