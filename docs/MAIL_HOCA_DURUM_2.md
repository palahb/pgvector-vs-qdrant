# Hocaya ikinci durum maili (TASLAK, gönderilmedi)

Gönderen: Burak. Bu dosya bir taslaktır, gönderme kararı Burak'ındır.

---

**Konu:** Re: CMP653 ders rapor çalışmanı makaleye dönüştürme hakkında

Hocam merhaba,

Daha önce gönderdiğim mailimdeki üç sorunun (kapsam, dergi, son tarih) cevabı hâlâ açık olduğu için kısa bir ilerleme özeti ve
karar bekleyen konuları yazıyorum. Metin ve kodlar şu branch'te:
https://github.com/palahb/pgvector-vs-qdrant/tree/paper-full-revision

**Referee raporundaki maddelerden neler yapıldı.** Yeni deneylerin (E6–E18) sonuçları
doğrulayıcıdan hatasız ve uyarısız geçti ve her biri commit, job numarası ve dosya özetleriyle bir
manifeste bağlı. İlk E1–E5 sonuçları şema denetiminden geçti ama eski koşular oldukları için
commit ve seed bilgileri eksik, bu açıkça işaretli:

- **M1/M2 (gecikme ve CPU):** Qdrant'ın gecikme avantajı segment sayısıyla büyüyor, CPU
  maliyeti farkı ise küçülüyor (1M, eşleşmiş recall 0,95: gecikme oranı 2,9–4,4×, sorgu başına
  CPU oranı 1,7–1,0×). Başlıktaki "3–4× hızlı motor" ifadesi bu yüzden "düşük tek istemci
  gecikmesi" olarak değişti ve CPU ile birlikte veriliyor.
- **M6/M7:** Tablo 5–Şekil 3 farkı veri hatası değil, farklı `ef` noktalarıymış. Her HNSW ayarı
  üç bağımsız build ile tekrarlandı. Sorgu başına recall dağılımı eklendi: ortalama recall 0,95
  iken sorguların yaklaşık %6'sı yüksek boyutta 0,8'in altında, iki motorda da aynı.
- **M3/M4 (build):** Qdrant paralel akış ve ertelenmiş indeksleme ile 356 s yerine 206 s'de
  kuruluyor (1M). pgvector'ün 1M yüklemesi WAL ile sınırlı (tablo `UNLOGGED` yapılınca
  yükleme 93 s'den 22 s'ye iniyor; yükleme aşaması 4,6 GB, indeks derlemesi 4,5 GB WAL yazıyor). Sonuç: "hangisi daha hızlı build ediyor" karşılaştırılan
  yapılandırmaya bağlı, eski iddia geri çekildi.
- **M5 (bellek):** Tam sorgu seti, üç tekrar, soğuk ve kararlı durum ayrı. Eski deneydeki 300
  sorgu gerçekten grafın küçük bir kısmına dokunuyormuş: pgvector 8 GB limitte eskiden 3,6 ms
  görünürken tam sorgu setiyle 636 ms. Qdrant 8 GB'a kadar bellek içi hızında.
- **M12 (planner):** 360 plan hücresinde (100K–1M, 128–1024 boyut) varsayılan planlayıcı
  hücrelerin %2,5'inde indeksi bırakıp taramaya düşüyor, hepsi 768 ve 1024 boyutta.

**Kendi hatalarım (düzeltildi):** pgvector `ef_search` değerini 1000'in üzerinde sessizce
reddediyormuş, E6 ve E8'deki `ef=1024` satırları gerçekte `ef=40` ile ölçülmüş. Raporlanan
eşleşmiş değerlerin hiçbiri bu satırlara dayanmıyor ve toplamlar değişmedi. Ayrıca Zhang vd.
makalesi pgvector'ü değil PASE'i inceliyormuş, metin düzeltildi.

**Sizden beklediğim kararlar:**

1. **Kapsam:** Filtreli arama, karma okuma-yazma, hibrit arama, açık döngü ve çok çekirdekli
   ölçekleme, quantization, 10M ölçek ve ikinci embedding modelini (M8, M9, M10) bu sürümde
   kapsam dışı bırakıp başlığı "RAG workloads" yerine filtresiz ANN aramasına daraltmayı
   öneriyorum. Uygun mu?
2. **Hedef dergi ve şablon:** Bu kapsamla Information Systems gerçekçi mi, yoksa Journal of
   Systems and Software / PeerJ CS gibi bir alternatif mi? Şablona geçişi dergi kesinleşince
   yapacağım.
3. **Son tarih** var mı?
4. **pgvector'e bildirim:** Planlayıcı bulgusu için issue metni ve tekrar üretici örnek taslağı
   hazır (`docs/PGVECTOR_ISSUE_DRAFT.md`). Mekanizmayı pgvector kaynağıyla karşılaştırdım: maliyet
   formülü 20 build'in 20'sinde indeks maliyetinin düştüğü `ef` değerini doğru öngörüyor. Örnek
   betiği henüz çalıştırmadım. Onayınızla önce çalıştırıp sonra göndermeyi öneriyorum.
5. **Yapay zekâ beyanı:** Taslak hazır (Claude, GPT/Codex kullanımı). Sizin Claude ve Gemini
   ile ürettiğiniz değerlendirme ve plan dokümanlarını beyanda ayrıca anmamı ister misiniz?

**Eksikler:** pgvector'ün bellek sınırı 4 GB'taki kolları 3 saatlik job limitinde bitmedi,
makalede "tamamlanmadı" olarak yazıyor. LaTeX metnini kendi makinemde derleyemedim, Overleaf'te
derleyip biçim kontrolü yapacağım.

Saygılarımla,
Burak
