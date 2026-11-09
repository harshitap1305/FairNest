import React from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Box, Paper, Typography, IconButton, Tooltip, Chip } from '@mui/material'
import DragHandleIcon from '@mui/icons-material/DragHandle'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import DeleteIcon from '@mui/icons-material/Delete'

function RankItem({ item, index, total, onMoveUp, onMoveDown, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.uid })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const isFloor = item.kind === 'FLOOR'

  return (
    <Paper
      ref={setNodeRef}
      style={style}
      variant="outlined"
      sx={{
        display: 'flex',
        alignItems: 'center',
        px: 1.5,
        py: 1,
        mb: 1,
        gap: 1,
        bgcolor: isDragging ? 'action.hover' : 'background.paper',
      }}
    >
      <IconButton size="small" {...attributes} {...listeners} sx={{ cursor: 'grab', mr: 0.5 }}>
        <DragHandleIcon fontSize="small" />
      </IconButton>

      <Chip label={`#${index + 1}`} size="small" color="primary" sx={{ minWidth: 36 }} />

      <Box sx={{ flexGrow: 1 }}>
        <Box display="flex" alignItems="center" gap={0.75}>
          <Typography variant="body2" fontWeight={600}>
            {isFloor ? `Any Room on Floor ${item.floor_no}` : `Room ${item.room_no || item.room_id}`}
          </Typography>
          <Chip
            label={isFloor ? 'FLOOR' : 'ROOM'}
            size="small"
            variant="outlined"
            color={isFloor ? 'secondary' : 'default'}
            sx={{ height: 18, fontSize: '0.65rem' }}
          />
        </Box>
        <Typography variant="caption" color="text.secondary">
          {isFloor
            ? 'Matches lowest available room number on this floor'
            : [
                item.floor_no != null ? `Floor ${item.floor_no}` : null,
                item.capacity ? `Cap ${item.capacity}` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
        </Typography>
      </Box>

      <Tooltip title="Move up">
        <span>
          <IconButton size="small" onClick={() => onMoveUp(index)} disabled={index === 0}>
            <ArrowUpwardIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="Move down">
        <span>
          <IconButton size="small" onClick={() => onMoveDown(index)} disabled={index === total - 1}>
            <ArrowDownwardIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="Remove">
        <IconButton size="small" onClick={() => onRemove(index)} color="error">
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Paper>
  )
}

/**
 * Drag-and-drop sortable rank list for ROOM and FLOOR preferences.
 */
export default function RankList({ items = [], onChange }) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return
    const oldIndex = items.findIndex((i) => i.uid === active.id)
    const newIndex = items.findIndex((i) => i.uid === over.id)
    if (oldIndex >= 0 && newIndex >= 0) {
      onChange(arrayMove(items, oldIndex, newIndex))
    }
  }

  const moveUp = (index) => {
    if (index === 0) return
    onChange(arrayMove(items, index, index - 1))
  }

  const moveDown = (index) => {
    if (index === items.length - 1) return
    onChange(arrayMove(items, index, index + 1))
  }

  const remove = (index) => {
    onChange(items.filter((_, i) => i !== index))
  }

  if (items.length === 0) {
    return (
      <Box
        sx={{
          border: '2px dashed',
          borderColor: 'divider',
          borderRadius: 2,
          p: 3,
          textAlign: 'center',
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No preferences selected. Click rooms in the grid or add a floor preference to rank them here.
        </Typography>
      </Box>
    )
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={items.map((i) => i.uid)} strategy={verticalListSortingStrategy}>
        {items.map((item, index) => (
          <RankItem
            key={item.uid}
            item={item}
            index={index}
            total={items.length}
            onMoveUp={moveUp}
            onMoveDown={moveDown}
            onRemove={remove}
          />
        ))}
      </SortableContext>
    </DndContext>
  )
}
