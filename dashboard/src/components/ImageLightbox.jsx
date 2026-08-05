import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Картинка во весь экран — как в мессенджерах.
 *
 * Кадры в раскадровке живут миниатюрами в 104 пикселя: вертикальный кадр во всю
 * ширину карточки растягивал список на десять тысяч пикселей. Но именно кадр —
 * то, что человек утверждает перед платной генерацией, и решение «этот человек
 * или не этот, мягко или резко» по миниатюре не принимается. Отсюда просмотр:
 * список остаётся коротким, а рассмотреть можно.
 *
 * `object-contain`, а не `cover`: обрезанный кадр здесь бессмысленен — смотрят
 * как раз на края и на пропорции лица.
 */
export default function ImageLightbox({ src, alt = '', caption = '', onClose }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!src) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKey);
    // Фон не должен уезжать под открытой картинкой: список раскадровки длинный,
    // и прокрутка «сквозь» просмотрщик читается как сломанная страница.
    const scrollBefore = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = scrollBefore;
    };
  }, [src, onClose]);

  if (!src) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={alt || 'Просмотр кадра'}
      // Клик по фону закрывает, клик по самой картинке — нет: иначе просмотр
      // захлопывается при попытке ткнуть в деталь, которую и пришли смотреть.
      onClick={onClose}
      className="fixed inset-0 z-[120] flex flex-col items-center justify-center gap-3 bg-black/90 p-4 backdrop-blur-sm"
    >
      <button
        ref={closeRef}
        type="button"
        onClick={onClose}
        aria-label="Закрыть просмотр"
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-zinc-300 transition-colors hover:bg-white/20 hover:text-white"
      >
        <X size={18} />
      </button>
      <img
        src={src}
        alt={alt}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[88vh] max-w-full rounded-lg object-contain shadow-2xl"
      />
      {caption && (
        <p className="max-w-full truncate text-center text-[11px] text-zinc-400">{caption}</p>
      )}
    </div>
  );
}
