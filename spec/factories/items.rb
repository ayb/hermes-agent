FactoryBot.define do
  factory :item do
    user
    location
    sequence(:name) { |n| "Item #{n}" }
    description { "A test item description" }
    buy_from { "Test Store" }
    min_quantity { "10.00".to_d }
    current_quantity { "5.00".to_d }
  end
end
