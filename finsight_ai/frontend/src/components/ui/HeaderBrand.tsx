interface HeaderBrandProps {
  showTagline?: boolean;
}

export function HeaderBrand({ showTagline = true }: HeaderBrandProps) {
  return (
    <div className="flex items-center gap-3">
      <img
        src="/mascot.png"
        alt="Coral"
        className="w-9 h-9 object-contain rounded-xl"
      />
      <div>
        <div className="text-lg font-bold leading-none text-gradient-coral">
          Coral
        </div>
        {showTagline && (
          <div className="text-xs text-ocean-DEFAULT/50 mt-0.5">
            Local · Private
          </div>
        )}
      </div>
    </div>
  );
}
