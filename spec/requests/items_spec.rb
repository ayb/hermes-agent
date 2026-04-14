require 'rails_helper'

RSpec.describe "Items", type: :request do
  let(:user) { create(:user) }
  let(:location) { create(:location, user: user) }
  let(:valid_item_attributes) {
    {
      name: "Test Item",
      description: "A test description",
      buy_from: "Test Store",
      min_quantity: 10.0,
      current_quantity: 5.0,
      location_id: location.id
    }
  }
  let(:invalid_item_attributes) {
    {
      name: "",
      description: "A test description",
      location_id: location.id
    }
  }

  before { sign_in user }

  describe "GET /items" do
    context "when user is authenticated" do
      it "returns a successful response" do
        create(:item, user: user, location: location)
        get items_path
        expect(response).to have_http_status(:success)
      end

      it "only shows items belonging to the current user" do
        item = create(:item, user: user, location: location)
        other_user = create(:user)
        _other_item = create(:item, user: other_user)

        get items_path
        expect(response.body).to include(item.name)
        expect(response.body).not_to include("Item 1")
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        get items_path
        expect(response).to redirect_to(new_session_path)
      end
    end
  end

  describe "GET /items/:id" do
    let(:item) { create(:item, user: user, location: location) }

    context "when user is authenticated" do
      it "returns a successful response" do
        get item_path(item)
        expect(response).to have_http_status(:success)
      end

      it "shows item details" do
        get item_path(item)
        expect(response.body).to include(item.name)
        expect(response.body).to include(item.description)
        expect(response.body).to include(item.buy_from)
      end
    end

    context "when item does not belong to user" do
      let(:other_user) { create(:user) }
      let(:other_item) { create(:item, user: other_user) }

      it "returns a 404 response" do
        expect {
          get item_path(other_item)
        }.to raise_error(ActiveRecord::RecordNotFound)
      end
    end
  end

  describe "GET /items/new" do
    context "when user is authenticated" do
      it "returns a successful response" do
        get new_item_path
        expect(response).to have_http_status(:success)
      end

      it "renders the new item form" do
        get new_item_path
        expect(response.body).to include('New Item')
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        get new_item_path
        expect(response).to redirect_to(new_session_path)
      end
    end
  end

  describe "POST /items" do
    context "with valid parameters" do
      it "creates a new item" do
        expect {
          post items_path, params: { item: valid_item_attributes }
        }.to change(Item, :count).by(1)
      end

      it "redirects to the created item" do
        post items_path, params: { item: valid_item_attributes }
        expect(response).to redirect_to(item_path(Item.last))
      end

      it "sets the current user as the owner" do
        post items_path, params: { item: valid_item_attributes }
        expect(Item.last.user).to eq(user)
      end

      it "sets the flash notice" do
        post items_path, params: { item: valid_item_attributes }
        expect(flash[:notice]).to eq("Item was successfully created.")
      end
    end

    context "with invalid parameters" do
      it "does not create a new item" do
        expect {
          post items_path, params: { item: invalid_item_attributes }
        }.not_to change(Item, :count)
      end

      it "renders the new template with unprocessable_entity status" do
        post items_path, params: { item: invalid_item_attributes }
        expect(response).to have_http_status(:unprocessable_entity)
        expect(response).to render_template(:new)
      end

      it "displays error messages" do
        post items_path, params: { item: invalid_item_attributes }
        expect(response.body).to include('error')
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        post items_path, params: { item: valid_item_attributes }
        expect(response).to redirect_to(new_session_path)
      end

      it "does not create an item" do
        expect {
          post items_path, params: { item: valid_item_attributes }
        }.not_to change(Item, :count)
      end
    end
  end

  describe "GET /items/:id/edit" do
    let(:item) { create(:item, user: user, location: location) }

    context "when user is authenticated" do
      it "returns a successful response" do
        get edit_item_path(item)
        expect(response).to have_http_status(:success)
      end

      it "renders the edit item form" do
        get edit_item_path(item)
        expect(response.body).to include('Edit Item')
        expect(response.body).to include(item.name)
      end
    end

    context "when item does not belong to user" do
      let(:other_user) { create(:user) }
      let(:other_item) { create(:item, user: other_user) }

      it "returns a 404 response" do
        expect {
          get edit_item_path(other_item)
        }.to raise_error(ActiveRecord::RecordNotFound)
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        get edit_item_path(item)
        expect(response).to redirect_to(new_session_path)
      end
    end
  end

  describe "PATCH /items/:id" do
    let(:item) { create(:item, user: user, location: location) }
    let(:new_attributes) {
      {
        name: "Updated Item Name",
        description: "Updated description",
        buy_from: "Updated Store",
        min_quantity: 15.0,
        current_quantity: 8.0
      }
    }

    context "with valid parameters" do
      it "updates the requested item" do
        patch item_path(item), params: { item: new_attributes }
        item.reload
        expect(item.name).to eq("Updated Item Name")
        expect(item.description).to eq("Updated description")
        expect(item.min_quantity).to eq(15.0)
        expect(item.current_quantity).to eq(8.0)
      end

      it "redirects to the item" do
        patch item_path(item), params: { item: new_attributes }
        expect(response).to redirect_to(item_path(item))
      end

      it "sets the flash notice" do
        patch item_path(item), params: { item: new_attributes }
        expect(flash[:notice]).to eq("Item was successfully updated.")
      end
    end

    context "with invalid parameters" do
      it "does not update the item" do
        original_name = item.name
        patch item_path(item), params: { item: { name: "" } }
        item.reload
        expect(item.name).to eq(original_name)
      end

      it "renders the edit template with unprocessable_entity status" do
        patch item_path(item), params: { item: { name: "" } }
        expect(response).to have_http_status(:unprocessable_entity)
        expect(response).to render_template(:edit)
      end

      it "displays error messages" do
        patch item_path(item), params: { item: { name: "" } }
        expect(response.body).to include('error')
      end
    end

    context "when item does not belong to user" do
      let(:other_user) { create(:user) }
      let(:other_item) { create(:item, user: other_user) }

      it "does not update the item" do
        expect {
          patch item_path(other_item), params: { item: new_attributes }
        }.to raise_error(ActiveRecord::RecordNotFound)
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        patch item_path(item), params: { item: new_attributes }
        expect(response).to redirect_to(new_session_path)
      end

      it "does not update the item" do
        original_name = item.name
        patch item_path(item), params: { item: new_attributes }
        item.reload
        expect(item.name).to eq(original_name)
      end
    end
  end

  describe "DELETE /items/:id" do
    let!(:item) { create(:item, user: user, location: location) }

    context "when user is authenticated" do
      it "destroys the requested item" do
        expect {
          delete item_path(item)
        }.to change(Item, :count).by(-1)
      end

      it "redirects to the items list" do
        delete item_path(item)
        expect(response).to redirect_to(items_path)
      end

      it "sets the flash notice" do
        delete item_path(item)
        expect(flash[:notice]).to eq("Item was successfully deleted.")
      end
    end

    context "when item does not belong to user" do
      let(:other_user) { create(:user) }
      let!(:other_item) { create(:item, user: other_user) }

      it "does not destroy the item" do
        expect {
          delete item_path(other_item)
        }.to raise_error(ActiveRecord::RecordNotFound)
        expect(Item.exists?(other_item.id)).to be true
      end
    end

    context "when user is not authenticated" do
      before { sign_out user }

      it "redirects to login page" do
        delete item_path(item)
        expect(response).to redirect_to(new_session_path)
      end

      it "does not destroy the item" do
        expect {
          delete item_path(item)
        }.not_to change(Item, :count)
      end
    end
  end
end
