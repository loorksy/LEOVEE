export type WatchlistSymbol = {
  code: string;
  item_id: string;
  last_price: number | null;
};

export type WatchlistData = {
  id: string;
  name: string;
  symbols: WatchlistSymbol[];
};

export type WatchlistListResponse = {
  items: WatchlistData[];
  ws_symbols: string[];
};
