FactoryBot.define do
  factory :inventory_change do
    user
    item
    location
    quantity { "15.00".to_d }
    quantity_change { "10.00".to_d }
    notes { "Restocked from supplier" }

    trait :skip_callback do
      after(:build) { |change| change.define_singleton_method(:update_item_inventory) {} }
    end
  end
end
