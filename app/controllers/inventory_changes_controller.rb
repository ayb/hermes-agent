class InventoryChangesController < ApplicationController
  before_action :set_item, only: [:new, :create]
  before_action :set_locations
  before_action :require_authentication

  def show
    @inventory_change = current_user.inventory_changes.find(params[:id])
  end

  def new
    if params[:item_id]
      @inventory_change = @item.inventory_changes.build
    else
      @inventory_change = current_user.inventory_changes.build
    end
    @items_for_select = current_user.items.order(:name)
  end

  def create
    @inventory_change = current_user.inventory_changes.build(inventory_change_params)

    if @inventory_change.save
      redirect_to redirect_after_create, notice: "Inventory adjustment was successfully recorded."
    else
      @items_for_select = current_user.items.order(:name)
      render :new, status: :unprocessable_entity
    end
  end

  private

  def inventory_change_params
    params.require(:inventory_change).permit(
      :item_id,
      :location_id,
      :quantity,
      :quantity_change,
      :notes
    )
  end

  def set_item
    @item = current_user.items.find(params[:item_id]) if params[:item_id]
  end

  def set_locations
    @locations = current_user.locations
  end

  def redirect_after_create
    if @inventory_change.location
      inventory_path(@inventory_change.location)
    elsif @inventory_change.item
      item_path(@inventory_change.item)
    else
      inventory_changes_path
    end
  end
end
