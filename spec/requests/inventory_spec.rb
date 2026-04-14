require 'rails_helper'

RSpec.describe "Inventory", type: :request do
  let(:user) { create(:user) }
  let(:location) { create(:location, user: user) }
  let(:other_location) { create(:location, user: user) }
  let(:item) { create(:item, user: user, location: location) }

  before { sign_in user }

  describe "GET /inventory" do
    context "when user is authenticated" do
      it "returns a successful response" do
        get inventory_index_path
        expect(response).to have_http_status(:success)
      end

      it "shows locations list" do
        location
        other_location
        get inventory_index_path
        expect(response.body).to include(location.name)
        expect(response.body).to include(other_location.name)
      end

      it "only shows locations belonging to the current user" do
        location
        other_user = create(:user)
        other_user_location = create(:location, user: other_user)

        get inventory_index_path
        expect(response.body).to include(location.name)
        expect(response.body).not_to include(other_user_location.name)
      end

      it "shows summary counts" do
        location
        other_location
        create(:item, user: user, location: location)
        create(:item, user: user, location: location)

        get inventory_index_path
        expect(response.body).to include("2")
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        get inventory_index_path
        expect(response).to redirect_to(new_session_path)
      end
    end

    context "when user has no locations" do
      it "returns a successful response with empty state" do
        get inventory_index_path
        expect(response).to have_http_status(:success)
        expect(response.body).to include("No locations")
      end
    end
  end

  describe "GET /inventory/:id" do
    context "when user is authenticated" do
      before do
        item
      end

      it "returns a successful response" do
        get inventory_path(location)
        expect(response).to have_http_status(:success)
      end

      it "shows items for the specified location" do
        create(:item, user: user, location: location, name: "Second Item")
        get inventory_path(location)
        expect(response.body).to include(item.name)
        expect(response.body).to include("Second Item")
      end

      it "only shows items from the specified location" do
        other_location_item = create(:item, user: user, location: other_location)
        get inventory_path(location)
        expect(response.body).to include(item.name)
        expect(response.body).not_to include(other_location_item.name)
      end

      it "shows item details" do
        get inventory_path(location)
        expect(response.body).to include(item.name)
        expect(response.body).to include(item.description)
        expect(response.body).to include(item.current_quantity.to_s)
        expect(response.body).to include(item.min_quantity.to_s)
      end

      it "shows location information" do
        get inventory_path(location)
        expect(response.body).to include(location.name)
        expect(response.body).to include(location.description) if location.description
      end

      context "with inventory changes" do
        let!(:inventory_change) {
          create(:inventory_change, user: user, item: item, location: location, notes: "Restocked today")
        }

        it "shows recent inventory changes" do
          get inventory_path(location)
          expect(response.body).to include("Restocked today")
        end
      end
    end

    context "when location does not belong to user" do
      let(:other_user) { create(:user) }
      let(:unauthorized_location) { create(:location, user: other_user) }

      it "returns a 404 response" do
        expect {
          get inventory_path(unauthorized_location)
        }.to raise_error(ActiveRecord::RecordNotFound)
      end
    end

    context "when location does not exist" do
      it "returns a 404 response" do
        expect {
          get inventory_path(id: 99999)
        }.to raise_error(ActiveRecord::RecordNotFound)
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        get inventory_path(location)
        expect(response).to redirect_to(new_session_path)
      end
    end

    context "with low quantity items" do
      let!(:low_quantity_item) {
        create(:item, user: user, location: location, current_quantity: 1.0, min_quantity: 10.0)
      }
      let!(:sufficient_item) {
        create(:item, user: user, location: location, current_quantity: 15.0, min_quantity: 10.0)
      }

      it "highlights low quantity items" do
        get inventory_path(location)
        expect(response.body).to include("low")
        expect(response.body).to include(sufficient_item.name)
      end
    end

    context "with empty location" do
      let(:empty_location) { create(:location, user: user) }

      it "returns a successful response with empty state" do
        get inventory_path(empty_location)
        expect(response).to have_http_status(:success)
        expect(response.body).to include("No items")
        expect(response.body).to include(empty_location.name)
      end
    end
  end
end
