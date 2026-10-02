import React, { useState } from 'react';
import { X, CheckCircle2, AlertCircle } from 'lucide-react';
import { AppSettings, UserProfile, WithdrawalMethod } from '../types';
import { requestWithdrawal } from '../services/store';
import { triggerHaptic } from '../services/telegram';

interface WithdrawModalProps {
  user: UserProfile;
  settings: AppSettings;
  onClose: () => void;
  onSuccess: () => void;
}

export const WithdrawModal: React.FC<WithdrawModalProps> = ({
  user,
  settings,
  onClose,
  onSuccess,
}) => {
  const [method, setMethod] = useState<WithdrawalMethod>('upi');
  const [amount, setAmount] = useState<string>(String(Math.max(settings.minWithdrawalLimit, 20)));
  const [upiId, setUpiId] = useState('');
  const [accountHolder, setAccountHolder] = useState(user.name);
  const [accountNumber, setAccountNumber] = useState('');
  const [bankName, setBankName] = useState('');
  const [ifsc, setIfsc] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const numAmount = parseFloat(amount);
    if (isNaN(numAmount) || numAmount < settings.minWithdrawalLimit) {
      setError(`Minimum withdrawal amount is ₹${settings.minWithdrawalLimit}`);
      triggerHaptic('error');
      return;
    }

    if (numAmount > user.balance) {
      setError(`Insufficient balance! Your available balance is ₹${user.balance.toFixed(2)}`);
      triggerHaptic('error');
      return;
    }

    if (method === 'upi') {
      if (!upiId.trim() || !upiId.includes('@')) {
        setError('Please enter a valid UPI ID (e.g. username@okhdfcbank or 9876543210@paytm)');
        triggerHaptic('error');
        return;
      }
    } else {
      if (!accountNumber.trim() || accountNumber.length < 8) {
        setError('Please enter a valid Bank Account Number');
        triggerHaptic('error');
        return;
      }
      if (!ifsc.trim() || ifsc.length < 5) {
        setError('Please enter a valid IFSC code (e.g. HDFC0001234)');
        triggerHaptic('error');
        return;
      }
    }

    setIsSubmitting(true);
    triggerHaptic('medium');

    const result = requestWithdrawal({
      userId: user.id,
      userName: user.name,
      amount: numAmount,
      method,
      upiId: method === 'upi' ? upiId.trim() : undefined,
      accountHolder: method === 'bank' ? accountHolder.trim() : undefined,
      accountNumber: method === 'bank' ? accountNumber.trim() : undefined,
      bankName: method === 'bank' ? bankName.trim() : undefined,
      ifsc: method === 'bank' ? ifsc.trim().toUpperCase() : undefined,
    });

    setIsSubmitting(false);

    if (result.success) {
      triggerHaptic('success');
      onSuccess();
    } else {
      setError(result.error || 'Failed to submit withdrawal request');
      triggerHaptic('error');
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white w-full max-w-sm rounded-[28px] p-5 shadow-2xl animate-scale-up relative my-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-['Outfit'] font-black text-lg text-slate-800 leading-tight">
              Withdraw Cash
            </h3>
            <p className="text-[11px] text-slate-500 font-medium">
              Instant 100% Payout via UPI & Bank
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 flex items-center justify-center font-bold text-xs"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Available Balance Banner */}
        <div className="bg-[#0a192f] text-white rounded-2xl px-4 py-2.5 mb-3 flex items-center justify-between">
          <div>
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">
              AVAILABLE BALANCE
            </span>
            <span className="font-['Outfit'] font-black text-xl text-[#38bdf8]">
              ₹ {user.balance.toFixed(2)}
            </span>
          </div>
          <div className="text-right">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">
              MINIMUM LIMIT
            </span>
            <span className="font-['Outfit'] font-bold text-xs text-amber-300">
              ₹ {settings.minWithdrawalLimit}
            </span>
          </div>
        </div>

        {/* Method Switcher Tabs */}
        <div className="grid grid-cols-2 gap-1.5 bg-slate-100 p-1 rounded-xl mb-3">
          <button
            type="button"
            onClick={() => setMethod('upi')}
            className={`py-1.5 text-xs font-['Outfit'] font-extrabold rounded-lg transition-all ${
              method === 'upi'
                ? 'bg-white text-[#0284c7] shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            ⚡ UPI Transfer
          </button>
          <button
            type="button"
            onClick={() => setMethod('bank')}
            className={`py-1.5 text-xs font-['Outfit'] font-extrabold rounded-lg transition-all ${
              method === 'bank'
                ? 'bg-white text-[#0284c7] shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            🏦 Bank Account
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2.5 rounded-xl mb-3 flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
            <span className="text-[11px] leading-tight">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-2.5">
          {/* Amount input */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] font-extrabold text-slate-600 uppercase tracking-wider">
                Withdrawal Amount (₹)
              </label>
              <span className="text-[10px] font-bold text-sky-600">
                Min ₹{settings.minWithdrawalLimit}
              </span>
            </div>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-xs">
                ₹
              </span>
              <input
                type="number"
                min={settings.minWithdrawalLimit}
                step="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
                className="w-full pl-7 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-['Outfit'] font-extrabold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0284c7]"
                placeholder={`Min ₹${settings.minWithdrawalLimit}`}
              />
            </div>
          </div>

          {method === 'upi' ? (
            <div>
              <label className="block text-[10px] font-extrabold text-slate-600 uppercase tracking-wider mb-1">
                UPI ID (VPA)
              </label>
              <input
                type="text"
                value={upiId}
                onChange={(e) => setUpiId(e.target.value)}
                required
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0284c7]"
                placeholder="e.g. 9876543210@paytm or name@okaxis"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="block text-[10px] font-extrabold text-slate-600 uppercase tracking-wider mb-1">
                  Account Holder Name
                </label>
                <input
                  type="text"
                  value={accountHolder}
                  onChange={(e) => setAccountHolder(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0284c7]"
                  placeholder="Full name as in passbook"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] font-extrabold text-slate-600 uppercase tracking-wider mb-1">
                    Account Number
                  </label>
                  <input
                    type="text"
                    value={accountNumber}
                    onChange={(e) => setAccountNumber(e.target.value)}
                    required
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0284c7]"
                    placeholder="Account Number"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-extrabold text-slate-600 uppercase tracking-wider mb-1">
                    IFSC Code
                  </label>
                  <input
                    type="text"
                    value={ifsc}
                    onChange={(e) => setIfsc(e.target.value.toUpperCase())}
                    required
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium uppercase text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0284c7]"
                    placeholder="HDFC0001234"
                  />
                </div>
              </div>
            </>
          )}

          {/* Prominent High-Visibility Withdrawal Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-gradient-to-r from-[#0284c7] via-[#0ea5e9] to-[#38bdf8] hover:from-[#0369a1] hover:to-[#0284c7] text-white font-['Outfit'] font-black text-xs sm:text-sm py-3 rounded-xl shadow-lg shadow-sky-600/30 flex items-center justify-center gap-1.5 active:scale-95 transition-all cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>CONFIRM WITHDRAWAL ⚡</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
