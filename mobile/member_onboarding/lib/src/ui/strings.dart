/// App wording in Hindi. Field labels come from the server with the form.
/// What the OTP steps say when they cannot go ahead.
class OtpWords {
  const OtpWords._();

  static const offline = 'नेटवर्क नहीं है। नेटवर्क आने पर OTP भेजें।';
  static const notSaved = 'फॉर्म अभी सहेजा नहीं गया। थोड़ी देर बाद फिर कोशिश करें।';
}

/// Said on the field itself when what was typed already belongs to someone else.
class Taken {
  const Taken._();

  static const aadhaar = 'यह आधार नंबर पहले से किसी फॉर्म या सदस्या का है। सही नंबर भरें।';
  static const mobile =
      'यह मोबाइल नंबर पहले से किसी फॉर्म या सदस्या का है। सदस्या का अपना नंबर भरें।';
  static const email = 'यह ईमेल पहले से किसी फॉर्म में है। सदस्या का अपना ईमेल भरें।';
  static const account = 'यह बैंक खाता पहले से किसी फॉर्म में है। सदस्या का अपना खाता भरें।';

  static String? forPath(String path) => switch (path) {
    'address.mobile' => mobile,
    'address.email' => email,
    'bank.account_number' => account,
    _ => null,
  };
}

class Strings {
  const Strings._();

  static const title = 'सदस्यता आवेदन';
  static const newForm = 'नया फॉर्म';
  static const chooseMpp = 'एम.पी.पी. चुनें';
  static const myDrafts = 'अधूरे फॉर्म';
  static const sentBack = 'सुधार के लिए लौटे फॉर्म';
  static const nothingHere = 'अभी कोई फॉर्म नहीं है';
  static const untitled = 'नाम नहीं भरा';
  static const loadFailed = 'जानकारी नहीं मिल पाई। इंटरनेट देखकर फिर कोशिश करें।';
  static const retry = 'फिर कोशिश करें';
  static const offlineReady = 'नेटवर्क नहीं है। फॉर्म भर सकते हैं, नेटवर्क आने पर भेजा जाएगा।';
  static const firstRunNeedsNetwork = 'पहली बार खोलने के लिए इंटरनेट ज़रूरी है।';

  static const myRecords = 'मेरे रिकॉर्ड';
  static const today = 'आज';
  static const yesterday = 'कल';
  static const thisWeek = 'इस हफ्ते';
  static const thisMonth = 'इस महीने';
  static const pickDates = 'तारीख चुनें';
  static const started = 'शुरू किए';
  static const sent = 'जमा किए';
  static const waiting = 'जाँच में';
  static const approved = 'सदस्य बने';
  static const returned = 'लौटे';
  static const all = 'सभी';
  static const drafts = 'अधूरे';
  static const showMore = 'और देखें';
  static const noRecords = 'इन तारीखों में कोई फॉर्म नहीं';
  static const startedOn = 'शुरू';
  static const sentOn = 'जमा';
  static const recordsNeedNetwork = 'रिकॉर्ड देखने के लिए इंटरनेट ज़रूरी है।';

  static const back = 'पीछे';
  static const next = 'आगे';
  static const step = 'चरण';
  static const required = 'यह भरना ज़रूरी है';
  static const optional = 'वैकल्पिक';
  static const choose = 'चुनें';
  static const fromMpp = 'एम.पी.पी. से';

  static const saved = 'सुरक्षित';
  static const saving = 'सहेजा जा रहा है';
  static const offline = 'फ़ोन में सुरक्षित, नेटवर्क आने पर भेजा जाएगा';
  static const conflict = 'यह फॉर्म कहीं और बदला गया है';
  static const useServerCopy = 'नई जानकारी लें';
  static const syncFailed = 'भेजने में समस्या आई';

  static const aadhaarNumber = 'आधार नंबर';
  static const aadhaarInvalid = 'सही 12 अंकों का आधार नंबर भरें';
  static const scanAadhaar = 'आधार QR स्कैन करें';
  static const scanHint = 'QR कोड को बॉक्स में रखें';
  static const scanFailed = 'QR नहीं पढ़ा जा सका, कृपया खुद भरें';
  static const scanCheck = 'स्कैन से भरी जानकारी एक बार जाँच लें';

  static const useLocation = 'अभी की लोकेशन लें';
  static const locationFailed = 'लोकेशन नहीं मिली। GPS चालू करके फिर कोशिश करें।';
  static const locationSaved = 'लोकेशन ली गई';

  static const accountNumber = 'बैंक खाता संख्या';
  static const accountAgain = 'खाता संख्या दोबारा भरें';
  static const accountMismatch = 'दोनों खाता संख्या एक जैसी नहीं हैं';

  static const family = 'परिवार के सदस्य';
  static const addPerson = 'सदस्य जोड़ें';
  static const removePerson = 'हटाएँ';
  static const name = 'नाम';
  static const gender = 'लिंग';
  static const age = 'उम्र';
  static const relation = 'संबंध';

  static const documents = 'दस्तावेज़';
  static const photo = 'सदस्या की फोटो';
  static const aadhaarFront = 'आधार का आगे का भाग';
  static const aadhaarBack = 'आधार का पीछे का भाग';
  static const passbook = 'बैंक पासबुक';
  static const takePhoto = 'फोटो लें';
  static const retake = 'दोबारा लें';
  static const memberSignature = 'सदस्या के हस्ताक्षर';
  static const signHere = 'यहाँ हस्ताक्षर करें';
  static const clear = 'मिटाएँ';
  static const saveSignature = 'हस्ताक्षर रखें';
  static const signatureSaved = 'हस्ताक्षर लिए गए';
  static const cannotWrite = 'हस्ताक्षर नहीं कर सकतीं? अंगूठे का निशान लें';
  static const thumbprint = 'अंगूठे का निशान';

  static const photoDark = 'फोटो बहुत अंधेरी है';
  static const photoBlurry = 'फोटो धुंधली लग रही है';
  static const photoHelp =
      'रोशनी में, फ़ोन स्थिर रखकर, कार्ड पूरा फ्रेम में रखकर दोबारा लें। धुंधली फोटो पर फॉर्म लौटाया जा सकता है।';
  static const keepAnyway = 'ऐसे ही रखें';
  static const photoDoubt = 'जाँच लें, फोटो साफ़ नहीं लग रही थी';

  static const verifyMobile = 'मोबाइल नंबर का सत्यापन';
  static const verifyEmail = 'ईमेल का सत्यापन';
  static const verified = 'सत्यापित';
  static const notVerified = 'सत्यापित नहीं';
  static const sendOtp = 'OTP भेजें';
  static const resendOtp = 'OTP दोबारा भेजें';
  static const resendIn = 'दोबारा भेजें';
  static const otpSent = 'सदस्या के फ़ोन पर OTP भेजा गया। उनसे पूछकर नीचे भरें।';
  static const otpSentEmail = 'सदस्या के ईमेल पर OTP भेजा गया। उनसे पूछकर नीचे भरें।';
  static const otpCode = '6 अंकों का OTP';
  static const checkOtp = 'जाँचें';
  static const enterMobileFirst = 'पहले मोबाइल नंबर भरें';
  static const enterEmailFirst = 'पहले ईमेल भरें';
  static const mobileNotVerified = 'मोबाइल नंबर सत्यापित नहीं है';

  static const review = 'जाँच करें';
  static const checklist = 'हर चरण की स्थिति';
  static const stepDone = 'पूरा';
  static const stepLeft = 'बाकी';
  static const toCorrect = 'इन्हें सुधारने के लिए लौटाया गया था';
  static const corrected = 'बदला गया';
  static const notCorrected = 'अभी नहीं बदला';
  static const stillNeeded = 'अभी ये बाकी हैं';
  static const allFilled = 'सब भर गया है। जमा कर सकते हैं।';
  static const submit = 'फॉर्म जमा करें';
  static const submitted = 'फॉर्म जमा हो गया';
  static const done = 'ठीक है';
  static const rejectedBecause = 'लौटाने का कारण';
  static const fixFirst = 'जमा नहीं हुआ। कृपया ये ठीक करें:';
  static const pleaseCheck = 'इन्हें ठीक करें, वरना फॉर्म जमा नहीं होगा';

  // Checked while typing, by the same rules the server applies on submit.
  static const aadhaarChecksum = 'यह आधार नंबर सही नहीं है। हर अंक कार्ड से मिलाकर देखें';
  static const accountInvalid = 'खाता संख्या 9 से 18 अंकों की होती है';
  static const mobileInvalid = 'मोबाइल नंबर 10 अंकों का हो और 6, 7, 8 या 9 से शुरू हो';
  static const pincodeInvalid = 'पिन कोड 6 अंकों का हो और 0 से शुरू न हो';
  static const emailInvalid = 'ईमेल सही नहीं है, जैसे name@gmail.com';
  static const ifscInvalid = 'IFSC 11 अक्षरों का होता है, जैसे SBIN0001234 (5वाँ अक्षर शून्य)';
  static const dateInvalid = 'तारीख सही नहीं है';
  static const applicantTooYoung = 'सदस्या की उम्र कम से कम 18 साल होनी चाहिए';
  static const applicantTooOld = 'उम्र 100 साल से ज़्यादा आ रही है। जन्म तिथि जाँचें';
  static const notANumber = 'सिर्फ़ अंक भरें, जैसे 5 या 5.5';
  static const productionNeeded = 'रोज़ का दूध उत्पादन 0 से ज़्यादा भरें';
  static const consumptionTooHigh = 'घर की खपत दूध उत्पादन से ज़्यादा नहीं हो सकती';
  static const noAnimals = 'कम से कम एक पशु की संख्या भरें';
  static const guardianNeeded = 'नामित 18 साल से छोटा है, संरक्षक का नाम भरें';
  static const guardianNotNeeded = 'नामित बालिग है, संरक्षक का नाम खाली छोड़ें';
  static const familyAgeInvalid = 'उम्र 0 से 120 साल के बीच भरें';
}
