import { NewsArticle } from '@/types/stock';

interface FocusSectionProps {
  articles: NewsArticle[];
  selectedCategories: string[];
  onCategorySelect: (categories: string[]) => void;
}

const FocusSection = ({ articles, selectedCategories, onCategorySelect }: FocusSectionProps) => {
  
  // Group by publisher domain: the same outlet reaches us under several
  // display names ("Barron's" from Google, "Barrons.com" from Finviz), and the
  // domain is the one stable identity.
  const availableCategories = [...new Set(
    articles.map(a => a.source_domain || a.source).filter(Boolean)
  )].sort();

  const toggleCategory = (category: string) => {
    if (selectedCategories.includes(category)) {
      onCategorySelect(selectedCategories.filter(c => c !== category));
    } else {
      onCategorySelect([...selectedCategories, category]);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">In Focus</h3>
      
      <div className="flex flex-wrap gap-2">
        {availableCategories.map((category) => (
          <button
            key={category}
            onClick={() => toggleCategory(category)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-all ${
              selectedCategories.includes(category)
                ? 'bg-primary text-primary-foreground border-primary shadow-[0_0_12px_hsl(var(--primary)/0.4)]'
                : 'bg-card/50 text-foreground border-border/50 hover:border-primary/50 hover:text-primary'
            }`}
          >
            {category}
          </button>
        ))}
      </div>
    </div>
  );
};

export default FocusSection;