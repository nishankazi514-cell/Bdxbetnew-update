BDXbet Ludo Admin Control

এই package মূল Ludo UI/design-এর বদলে দেয় না। shuvoludo.html-এ শুধু adminControl listener যোগ করা হয়েছে যাতে Admin থেকে Pause/Resume/Kick control real-time কাজ করে।

1) Render-এ আলাদা Web Service হিসেবে deploy করুন:
   Build: pip install -r requirements.txt
   Start: gunicorn admin_server:app

2) Environment Variables:
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=YOUR_STRONG_PASSWORD
   ADMIN_SECRET_KEY=YOUR_RANDOM_SECRET
   FIREBASE_DATABASE_URL=https://ludu-369-default-rtdb.asia-southeast1.firebasedatabase.app
   FIREBASE_SERVICE_ACCOUNT_JSON=YOUR_FIREBASE_SERVICE_ACCOUNT_JSON

3) Firebase Console -> Project Settings -> Service Accounts -> Generate new private key
   JSON file-এর পুরো content FIREBASE_SERVICE_ACCOUNT_JSON-এ দিন।
   Service account JSON কখনও HTML/JS-এ দেবেন না।

4) Admin URL:
   /login

Controls:
- Room list / live refresh
- Start / Pause / Resume / End
- Delete room
- Kick player
- Force turn
- Force dice 1-6
- Set pawn position (-1 to 56)
- Force winner
- Reset game

গুরুত্বপূর্ণ:
- বর্তমান betting/wallet settlement logic এখানে ইচ্ছামতো পরিবর্তন করা হয়নি।
- Admin "winner" control game state বদলায়; existing wallet/prize settlement যদি আলাদা client-side logic-এ থাকে, সেটি automatically admin payout হিসেবে ধরে নেওয়া যাবে না।
- Firebase Realtime Database rules-এর উপর Firebase Admin SDK server-side থেকে কাজ করে, তাই service account নিরাপদ রাখতে হবে।
