# Hocaya teslim maili (TASLAK, GÖNDERİLMEDİ)

Gönderen: Burak. Bu dosya bir taslaktır; göndermek ve metni değiştirmek sizin kararınızdır.

---

**Konu:** Re: CMP653 ders rapor çalışmanı makaleye dönüştürme hakkında: tam taslak

Hocam merhaba,

17 Kasım cevabınızdaki karara göre çalıştım ve makalenin tam taslağı hazır. Metin, kodlar ve ham sonuçların özetleri şu branch'te:
https://github.com/palahb/pgvector-vs-qdrant/tree/paper-full-revision (etiketler `harness-v1` ve `analysis-v2`). Makale Elsevier şablonunda (`paper/main.tex`), hedef Information Systems.

**Önce bir düzeltme.** Daha önce yazdığım mailde "qrels elimizde" demiştim; bunu referee raporundan almıştım ve doğrulamamıştım. O sırada qrels diskte yoktu. Sonradan indirdim ve ölçtüm.

**Ne yapıldı.** Başlık "RAG" olmadan, "Where Vector Search Benchmarks Go Wrong: A Controlled Comparison of pgvector and Qdrant". Geri çağırdığınız beş madde yapıldı:

1. *Nedensel analiz (E19).* pgvector, Qdrant'tan daha az vektör okuyor ama okuma başına yaklaşık 2,3 kat döngü harcıyor; döngülerinin yarısı mesafe hesabı ve eleman yükleme dışında (buffer manager ve defter tutma). Mesafe sayısını doğrudan ölçemedim (sayaç yok, root yok); vekil ve üst sınırlarla raporladım.
2. *`halfvec` ve `int8` (E20).* `halfvec` indeksi üçte bire indiriyor, hız ve recall'da ölçülebilir kayıp yok; `int8` Qdrant'ı sorgu başına 1,6 kat hızlandırıyor ama depolamayı küçültmüyor. "pgvector iki kat yer kaplıyor" bulgusu 32 bit yerleşimin özelliği olarak yeniden yazıldı.
3. *PgBouncer (E21).* Aşırı yükte p99'u yaklaşık yarıya indiriyor, verimi artırmıyor.
4. *Open-loop (E22).* %80 yükte pgvector'ün p99'u Qdrant'ınkinin yaklaşık iki katı; pgvector %95'te 90 saniyelik pencerede oturmadı, Qdrant oturdu.
5. *nDCG@10 (E23).* Korpusumuz (ilk 1M) yargılı ilgili belgelerin yalnızca %0,72'sini içeriyor. Kuralı ölçümden önce yazdım; sonuç "yalnızca duyarlılık analizi": recall 0,95'te yaklaşık arama, kesin aramanın nDCG@10'unun %98'ini koruyor. Mutlak etkinlik iddiası yok.

Tüm tablolar bir manifeste bağlı ve `make verify-paper` ham sonuçlardan analizleri yeniden üretiyor, başlık sayılarını ve tablo hücrelerini denetliyor (etiketli sürümde 30 adımın hepsi geçiyor). Bu denetim son turda yuvarlama kaynaklı dört küçük hata buldu; düzelttim. Ayrıntılar `docs/NE_DEGISTI.md` içinde.

**Sizden beklediklerim:**

1. *Information Systems'in "Guide for Authors"ı.* ScienceDirect sayfasını otomatik araçla açamadım (403). Kapsam, makale türü, uzunluk sınırı ve hakem modeli için bir tarayıcıda bakabilir misiniz? Metin bu konularda bir iddia taşımıyor.
2. *Yapay zekâ beyanı.* Taslak metinde kaynakçadan önce duruyor (Elsevier'in istediği yer). Kullandığım araçlar Claude ve GPT/Codex. Sizin Claude ve Gemini ile hazırladığınız değerlendirme belgelerini beyanda ayrıca anmamı ister misiniz? Son cümle yazarların taahhüdü, ikimizin de metni okuması gerekiyor.
3. *Beyanlar:* sorumlu yazar, yazar katkıları (CRediT), rakip çıkar, fonlama, ham sonuçların (yaklaşık 3 GB) nerede saklanacağı.
4. *pgvector planlayıcı bulgusu:* upstream'e issue açmak için taslak hazır; tekrar üretici betiği henüz çalıştırmadım. Onayınızla önce çalıştırıp sonra göndermeyi öneriyorum.

**Eksikler ve sınırlar.** Makaleyi derleyemedim (bu makinede TeX yok), Overleaf'te derleyip biçimi kontrol edeceğim. Koştuğumuz `hamsi` düğümlerinde NVMe yok (bir düğümde doğruladım; diğer bölümlere bakmadım), depolamaya bağlı sonuçlar "HDD, en kötü durum" diye işaretli. pgvector'ün 4 GB bellek sınırındaki kolları 3 saatlik limitte bitmedi, "tamamlanmadı" diye raporlanıyor. Qdrant'ın depolama boyutu aynı yapılandırmanın build'leri arasında yaklaşık üçte bir oynuyor, nedenini bulamadım.

Takvim: 22 Aralık'a kadar yorumlarınızı bekliyorum, 8 Ocak'ta göndermeyi hedefliyorum.

Saygılarımla,
Burak
