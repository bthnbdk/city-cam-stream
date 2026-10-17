OBS ŞABLONU — Istanbul
1) OBS > Sahne Koleksiyonu > İçe Aktar > obs_scenes_istanbul.json
2) Kamera kaynaklarındaki 'input' alanlarına ANCAK lisansı A/onaylı B olan akış URL'lerini yazın.
   (Şu an 4 aday kamera gömüldü, lisans sınıfı kontrol edilmeli.)
3) Overlay: Browser Source yerel dosya yolu ile çalışır (overlays/).
4) Rotasyon/otomatik yedek: python3 rotate.py --ws ws://localhost:4455 --pass <obs-ws-parola>
5) Ses: kamera sesini KAPAT (mixers), ambiyans/müzik ayrı bir kaynaktan (lisanlı) verilir.
