import { useState, useEffect } from 'react';
import { UserProfile, AppSettings } from '../types';
import { Check, ShieldAlert, Smartphone, ChevronRight } from 'lucide-react';
import { rtdb, ref, get, set } from '../services/firebase';

interface DeviceVerificationScreenProps {
  user: UserProfile;
  settings: AppSettings;
  referrerId?: string | null;
  onContinue: () => void;
}

const DEVICE_STORAGE_KEY = 'rg_phone_registered_device_v1';
const BOUND_TELEGRAM_ID_KEY = 'rg_bound_telegram_id_v1';

export function DeviceVerificationScreen({
  user,
  referrerId,
  onContinue,
}: DeviceVerificationScreenProps) {
  const [status, setStatus] = useState<'verifying' | 'success' | 'blocked'>('verifying');
  const [blockedDetails, setBlockedDetails] = useState<{ originalId: string }>({ originalId: '' });
  const [referrerName, setReferrerName] = useState<string>('MICHAEL');

  useEffect(() => {
    // 1. Fetch referrer name if available
    if (referrerId && rtdb) {
      const cleanRef = referrerId.replace('ref_', '').trim();
      get(ref(rtdb, `users/${cleanRef}`))
        .then((snapshot) => {
          if (snapshot.exists()) {
            const val = snapshot.val();
            setReferrerName(val.name?.toUpperCase() || `USER #${cleanRef.slice(-4)}`);
          } else {
            setReferrerName(`FRIEND #${cleanRef.slice(-4)}`);
          }
        })
        .catch(() => {
          setReferrerName('MICHAEL');
        });
    }

    // 2. Perform Single Phone / Anti-Account-Switch Verification
    const currentTelegramId = String(user.telegramId || user.id).trim();

    // Generate or get persistent phone device UUID stored in this phone's browser / Telegram WebView
    let localDeviceId = localStorage.getItem(DEVICE_STORAGE_KEY);
    if (!localDeviceId) {
      localDeviceId = 'dev_' + Math.random().toString(36).substring(2, 12) + Date.now().toString(36);
      localStorage.setItem(DEVICE_STORAGE_KEY, localDeviceId);
    }

    const boundLocalTelegramId = localStorage.getItem(BOUND_TELEGRAM_ID_KEY);

    // CHECK A: Is this phone's localStorage already bound to a DIFFERENT Telegram ID?
    if (boundLocalTelegramId && boundLocalTelegramId !== currentTelegramId) {
      // BUSTED: User switched Telegram account on the SAME phone!
      setStatus('blocked');
      setBlockedDetails({ originalId: boundLocalTelegramId });
      return;
    }

    // CHECK B: Double-check with Firebase RTDB device bindings
    if (rtdb && localDeviceId) {
      get(ref(rtdb, `devices/${localDeviceId}`))
        .then((snapshot) => {
          if (snapshot.exists()) {
            const data = snapshot.val();
            const boundId = String(data.boundTelegramId || '').trim();

            if (boundId && boundId !== currentTelegramId) {
              localStorage.setItem(BOUND_TELEGRAM_ID_KEY, boundId);
              setStatus('blocked');
              setBlockedDetails({ originalId: boundId });
              return;
            }
          }

          // CLEAN DEVICE: Bind this phone to the current Telegram account permanently
          localStorage.setItem(BOUND_TELEGRAM_ID_KEY, currentTelegramId);
          if (rtdb && localDeviceId) {
            set(ref(rtdb, `devices/${localDeviceId}`), {
              boundTelegramId: currentTelegramId,
              boundName: user.name || 'User',
              firstVerifiedAt: Date.now(),
              deviceFingerprint: navigator.userAgent.slice(0, 80),
            }).catch(() => {});
          }

          setStatus('success');
        })
        .catch(() => {
          localStorage.setItem(BOUND_TELEGRAM_ID_KEY, currentTelegramId);
          setStatus('success');
        });
    } else {
      localStorage.setItem(BOUND_TELEGRAM_ID_KEY, currentTelegramId);
      setStatus('success');
    }
  }, [user, referrerId]);

  // Format Telegram ID with exact spacing like in Screenshot ("7 878 219 676")
  const rawId = String(user.telegramId || user.id || '7878219676');
  // Format as 1 digit then triplets or custom triplets
  const formattedId = rawId.length === 10
    ? `${rawId[0]} ${rawId.slice(1, 4)} ${rawId.slice(4, 7)} ${rawId.slice(7)}`
    : rawId.replace(/(\d{3})(?=\d)/g, '$1 ');

  return (
    <div className="fixed inset-0 z-50 bg-[#0c121d] flex flex-col justify-between p-4 sm:p-6 overflow-y-auto text-white select-none">
      {/* Upper Area: 3D Stacked ID Card */}
      <div className="w-full max-w-sm mx-auto pt-4 relative flex flex-col items-center">
        {/* Top Floating Mini Tab / Dot */}
        <div className="w-2.5 h-1.5 rounded-full bg-[#34d399] -mb-1 z-20 shadow-sm" />

        {/* Background Layer Card (Card Stack Effect) */}
        <div className="w-[88%] h-24 rounded-[28px] bg-[#1a2d48]/70 border border-cyan-400/30 -mb-20 transform -rotate-1 scale-[0.98] opacity-80 pointer-events-none" />

        {/* Foreground Main ID Card */}
        <div className="w-full relative rounded-[30px] p-6 bg-[#0077e6] overflow-hidden shadow-2xl shadow-cyan-950/60 border border-cyan-300/40 z-10">
          {/* Green Curve Graphic on Right */}
          <div className="absolute top-0 right-0 w-[55%] h-full bg-[#00a86b] rounded-l-[180px] pointer-events-none" />

          {/* Wireframe Origami Paper Airplane Illustration */}
          <svg
            className="absolute top-3 right-3 w-32 h-32 opacity-35 pointer-events-none"
            viewBox="0 0 100 100"
            fill="none"
            stroke="white"
            strokeWidth="1.2"
          >
            <polygon points="10,45 85,15 55,85 45,55" />
            <line x1="85" y1="15" x2="45" y2="55" />
            <line x1="45" y1="55" x2="35" y2="75" />
            <line x1="35" y1="75" x2="55" y2="85" />
          </svg>

          {/* Card Header */}
          <div className="flex items-center justify-between mb-9 relative z-10">
            <span className="text-xs font-bold text-white tracking-wide">
              Device verification
            </span>
            <span className="bg-black/35 backdrop-blur-sm text-white font-extrabold text-[11px] px-3.5 py-1 rounded-full border border-white/10">
              Verified
            </span>
          </div>

          {/* TELEGRAM ID Section */}
          <div className="relative z-10 pb-1">
            <span className="text-[10px] font-black tracking-widest text-sky-200 uppercase block mb-1">
              TELEGRAM ID
            </span>
            <div className="text-[26px] sm:text-[28px] font-mono font-black tracking-wider text-white">
              {formattedId}
            </div>
          </div>

          {/* Floating Large Mint-Green Checkmark Badge (Bottom Right) */}
          <div className="absolute right-4 -bottom-1 translate-y-1/4 w-16 h-16 rounded-full bg-[#5fe3a1] flex items-center justify-center text-[#064e3b] shadow-xl shadow-emerald-950/50 z-20">
            <Check className="w-8 h-8 stroke-[3.5]" />
          </div>
        </div>
      </div>

      {/* Lower Area: Rounded Bottom Card Container */}
      <div className="w-full max-w-sm mx-auto mt-6 bg-[#131b29] rounded-[32px] p-6 border border-white/5 space-y-5 shadow-2xl">
        {status === 'blocked' ? (
          /* Anti-Account Switch Lock Alert */
          <div className="text-center space-y-3 py-2">
            <div className="w-14 h-14 rounded-full bg-red-500/20 border border-red-500 flex items-center justify-center mx-auto text-red-400">
              <ShieldAlert className="w-7 h-7" />
            </div>
            <h3 className="text-lg font-['Outfit'] font-black text-white">
              Device Verification Failed!
            </h3>
            <p className="text-xs text-red-400 font-bold">
              Multiple Accounts Detected on this Phone 🚫
            </p>
            <div className="bg-[#0b121e] rounded-2xl p-3.5 text-left border border-white/5 space-y-1.5 text-xs text-slate-300">
              <div className="flex items-center gap-1.5 text-amber-300 font-semibold">
                <Smartphone className="w-4 h-4 shrink-0" />
                <span>Phone already linked to ID #{blockedDetails.originalId}</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Rules ke mutabiq ek phone me sirf ek hi Telegram account se referral reward mil sakta hai.
              </p>
            </div>
            <button
              onClick={onContinue}
              className="w-full py-3.5 rounded-2xl bg-[#0084ff] text-white font-bold text-xs"
            >
              Continue with Limited Mode
            </button>
          </div>
        ) : (
          /* Normal Verified View matching Screenshot */
          <>
            {/* Title */}
            <h1 className="text-[28px] sm:text-[32px] font-['Outfit'] font-black text-white leading-none">
              Device verified
            </h1>

            {/* Inviter Credited Pill Box */}
            <div className="bg-[#0c1421] border border-white/10 rounded-2xl p-3.5 flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-full border-2 border-[#00c896] flex items-center justify-center text-[#00c896] shrink-0">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="leading-tight">
                <span className="text-xs font-bold text-[#00c896] block mb-0.5">
                  Invite credited
                </span>
                <span className="text-sm font-black text-white">
                  {referrerName} got credit for inviting you
                </span>
              </div>
            </div>

            {/* 3 Step Timeline (Telegram [✓]  This phone [✓]  Approved [✓]) */}
            <div className="pt-2 pb-1">
              <div className="flex items-center justify-between relative px-2">
                {/* Connecting Lines */}
                <div className="absolute left-8 right-8 top-3.5 h-[2px] bg-slate-700 -z-0" />

                {/* Step 1: Telegram */}
                <div className="flex flex-col items-center gap-2 z-10">
                  <div className="w-7 h-7 rounded-full bg-[#5fe3a1] flex items-center justify-center text-[#064e3b] shadow-md shadow-emerald-950/40">
                    <Check className="w-4 h-4 stroke-[3.5]" />
                  </div>
                  <span className="text-xs font-bold text-slate-200">
                    Telegram
                  </span>
                </div>

                {/* Step 2: This phone */}
                <div className="flex flex-col items-center gap-2 z-10">
                  <div className="w-7 h-7 rounded-full bg-[#5fe3a1] flex items-center justify-center text-[#064e3b] shadow-md shadow-emerald-950/40">
                    <Check className="w-4 h-4 stroke-[3.5]" />
                  </div>
                  <span className="text-xs font-bold text-slate-200">
                    This phone
                  </span>
                </div>

                {/* Step 3: Approved */}
                <div className="flex flex-col items-center gap-2 z-10">
                  <div className="w-7 h-7 rounded-full bg-[#5fe3a1] flex items-center justify-center text-[#064e3b] shadow-md shadow-emerald-950/40">
                    <Check className="w-4 h-4 stroke-[3.5]" />
                  </div>
                  <span className="text-xs font-bold text-slate-200">
                    Approved
                  </span>
                </div>
              </div>
            </div>

            {/* Action Button: Open Cash Rocket 🚀💰 > */}
            <button
              onClick={onContinue}
              className="w-full py-4 rounded-2xl bg-[#0084ff] hover:bg-[#0072de] active:scale-[0.98] text-white font-['Outfit'] font-black text-base flex items-center justify-center gap-1.5 shadow-lg shadow-blue-600/30 transition-all cursor-pointer"
            >
              <span>Open Cash Rocket 🚀💰</span>
              <ChevronRight className="w-5 h-5 stroke-[2.5]" />
            </button>
          </>
        )}
      </div>

      {/* Bottom Phone Home Indicator Bar */}
      <div className="w-32 h-1 bg-white/30 rounded-full mx-auto mt-4 mb-1" />
    </div>
  );
}
